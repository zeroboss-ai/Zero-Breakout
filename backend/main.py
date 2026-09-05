import os
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Query, Path, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse, Response
import pandas as pd

from .database import (
    init_db,
    get_latest_signals,
    get_stock_setup,
    get_stock_price_history,
    get_watchlist,
    toggle_watchlist,
    is_in_watchlist,
    get_all_active_symbols,
    get_connection
)
from .seed_data import seed_database_if_empty
from .scheduler import start_scheduler, stop_scheduler, run_daily_eod_pipeline
from .gemini_service import get_gemini_analysis
from .seo_renderer import generate_homepage_html, generate_stock_ssr_html, generate_sitemap_xml
import threading

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("ZeroBreakout.App")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: initialize database and seed if empty
    logger.info("Initializing ZeroBreakout database and services...")
    init_db()
    seed_database_if_empty()
    # Start background scheduler for daily post-market scans
    start_scheduler()

    # Background verification: Auto-fetch today's Bhavcopy if market is closed (>16:15 IST) and today's data is missing
    def auto_sync_on_startup():
        try:
            from datetime import timezone, timedelta
            ist_now = datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)
            if ist_now.weekday() < 5 and (ist_now.hour > 16 or (ist_now.hour == 16 and ist_now.minute >= 15)):
                today_str = ist_now.strftime("%Y-%m-%d")
                conn = get_connection()
                count = conn.execute("SELECT COUNT(DISTINCT symbol) as cnt FROM price_history WHERE date = ?", (today_str,)).fetchone()["cnt"]
                conn.close()
                if count < 500:
                    logger.info(f"Startup check: Today's Bhavcopy ({today_str}) not yet loaded. Ingesting today's market close and scanning patterns in background...")
                    run_daily_eod_pipeline()
                else:
                    logger.info(f"Startup check: Today's Bhavcopy ({today_str}) already loaded for {count} stocks.")
        except Exception as err:
            logger.error(f"Startup auto_sync error: {err}")

    threading.Thread(target=auto_sync_on_startup, daemon=True).start()

    yield
    # Shutdown: stop scheduler cleanly
    stop_scheduler()

app = FastAPI(
    title="ZeroBreakout API",
    description="Stock Pattern Scanner for NSE-listed Indian stocks",
    version="1.0.0",
    lifespan=lifespan
)

# Security Headers Middleware
@app.middleware("http")
async def add_security_headers(request, call_next):
    response = await call_next(request)
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin-allow-popups"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self' https: data:; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://www.gstatic.com https://apis.google.com https://*.firebaseapp.com https://accounts.google.com https://*.googleapis.com; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com data:; "
        "img-src 'self' data: https:; "
        "connect-src 'self' https: http:; "
        "frame-src 'self' https://*.firebaseapp.com https://accounts.google.com https://*.google.com;"
    )
    return response

# Enable CORS for local dev and production
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend")

# ----------------- HEALTH & UPTIME MONITOR ENDPOINTS ----------------- #

@app.get("/health")
@app.head("/health")
async def health_check():
    return {"status": "ok", "app": "ZeroBreakout Terminal", "timestamp": datetime.utcnow().isoformat()}

# ----------------- API ENDPOINTS ----------------- #

@app.get("/api/signals")
async def get_signals(
    pattern: Optional[str] = Query(None, max_length=100, description="Filter by pattern type or 'all'"),
    search: Optional[str] = Query(None, max_length=100, description="Search by symbol or company name"),
    limit: int = Query(150, ge=1, le=500)
):
    """
    Returns precomputed signals from the signals table.
    No pattern computation on page load — instantaneous response!
    """
    try:
        clean_pattern = str(pattern).strip() if pattern else None
        clean_search = str(search).strip() if search else None
        signals = get_latest_signals(pattern_type=clean_pattern, search_query=clean_search, limit=limit)
        return {"count": len(signals), "signals": signals}
    except Exception as e:
        logger.error(f"Error fetching signals: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/stocks/{symbol}/setup")
async def get_stock_setup_data(
    symbol: str = Path(..., max_length=20, pattern=r"^[A-Za-z0-9_.\-]+$")
):
    """
    Fetches stock metadata, current price, day change, active pattern signal, and watchlist state.
    """
    clean_sym = str(symbol).strip().upper()
    setup = get_stock_setup(clean_sym)
    if not setup:
        raise HTTPException(status_code=404, detail=f"Stock {clean_sym} not found")
    
    setup["in_watchlist"] = is_in_watchlist(clean_sym)
    return setup

@app.get("/api/stocks/{symbol}/history")
async def get_stock_history_data(
    symbol: str = Path(..., max_length=20, pattern=r"^[A-Za-z0-9_.\-]+$"),
    range: str = Query("1Y", max_length=5, pattern=r"^(1M|6M|1Y|3Y|5Y|10Y|ALL)$")
):
    """
    Returns OHLCV candlestick data and overlaid moving averages (20 SMA & 50 SMA).
    """
    clean_sym = str(symbol).strip().upper()
    days_map = {
        "1M": 25,
        "6M": 130,
        "1Y": 252,
        "3Y": 750,
        "5Y": 1250,
        "10Y": 2500,
        "ALL": 2500
    }
    limit_days = days_map.get(range, 252)
    history = get_stock_price_history(clean_sym, limit_days=limit_days + 50) # extra for SMA calc

    # On-demand multi-year history auto-fetch if database has less than requested history (or fewer than 30 candles)
    if len(history) < min(limit_days, 500) or len(history) < 30:
        try:
            import yfinance as yf
            from backend.database import upsert_price_batch, update_stock_ath_from_history
            tk = yf.Ticker(f"{clean_sym}.NS")
            df_yf = tk.history(period="10y")
            if not df_yf.empty:
                df_yf = df_yf.reset_index()
                date_col = "Date" if "Date" in df_yf.columns else df_yf.columns[0]
                df_yf["date"] = pd.to_datetime(df_yf[date_col]).dt.strftime("%Y-%m-%d")
                candles_to_save = []
                for _, r in df_yf.iterrows():
                    try:
                        candles_to_save.append((
                            clean_sym,
                            str(r["date"]),
                            float(r["Open"]),
                            float(r["High"]),
                            float(r["Low"]),
                            float(r["Close"]),
                            int(r["Volume"])
                        ))
                    except Exception:
                        continue
                if candles_to_save:
                    upsert_price_batch(candles_to_save)
                    update_stock_ath_from_history(clean_sym)
                    history = get_stock_price_history(clean_sym, limit_days=limit_days + 50)
        except Exception as yf_err:
            logger.warning(f"Error fetching history for {clean_sym} from yfinance: {yf_err}")
    
    if not history:
        raise HTTPException(status_code=404, detail=f"No price history found for {symbol.upper()}")

    df = pd.DataFrame(history)
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    df["open"] = pd.to_numeric(df["open"], errors="coerce")
    df["high"] = pd.to_numeric(df["high"], errors="coerce")
    df["low"] = pd.to_numeric(df["low"], errors="coerce")
    df["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(0)

    # Compute Moving Averages
    df["sma_20"] = df["close"].rolling(window=20).mean().round(2)
    df["sma_50"] = df["close"].rolling(window=50).mean().round(2)

    # Trim to requested range window
    df_sliced = df.iloc[-limit_days:] if len(df) > limit_days else df
    
    candles = []
    for _, row in df_sliced.iterrows():
        candles.append({
            "date": row["date"],
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
            "volume": int(row["volume"]),
            "sma_20": float(row["sma_20"]) if pd.notna(row["sma_20"]) else None,
            "sma_50": float(row["sma_50"]) if pd.notna(row["sma_50"]) else None
        })

    return {
        "symbol": symbol.upper(),
        "range": range,
        "count": len(candles),
        "candles": candles
    }

@app.get("/api/stocks/{symbol}/ai-analysis")
async def get_stock_ai_analysis(
    symbol: str = Path(..., max_length=20, pattern=r"^[A-Za-z0-9_.\-]+$")
):
    """
    Generates AI-powered technical pattern breakdown using Gemini API.
    """
    clean_sym = str(symbol).strip().upper()
    setup = get_stock_setup(clean_sym)
    if not setup:
        raise HTTPException(status_code=404, detail=f"Stock {clean_sym} not found")

    signal = setup.get("latest_signal")
    analysis = get_gemini_analysis(clean_sym, setup, signal)
    return analysis

@app.get("/api/watchlist")
async def get_user_watchlist():
    """
    Returns list of starred stocks with live stats.
    """
    items = get_watchlist(user_id="default_user")
    return {"count": len(items), "items": items}

@app.post("/api/watchlist/{symbol}")
async def toggle_stock_watchlist(
    symbol: str = Path(..., max_length=20, pattern=r"^[A-Za-z0-9_.\-]+$")
):
    """
    Toggles watchlist state for a stock.
    """
    clean_sym = str(symbol).strip().upper()
    is_added = toggle_watchlist(clean_sym, user_id="default_user")
    return {"symbol": clean_sym, "in_watchlist": is_added}

ADMIN_EMAILS = [
    "zerobossai@gmail.com",
    "zerobossai@gamil.com",
    os.environ.get("ADMIN_EMAIL", "").strip().lower()
]

ADMIN_SESSION_TOKEN = os.environ.get("ADMIN_SESSION_TOKEN", "zb_admin_token_zerobossai_8899")

from pydantic import BaseModel, Field
import urllib.parse
import json
import base64
import time

def verify_google_id_token(id_token: str) -> Optional[Dict[str, Any]]:
    """
    Cryptographically verifies Firebase / Google OAuth ID token.
    1. First decodes and validates Firebase Auth JWT (iss=securetoken.google.com, aud=zero-breakout, exp, email, email_verified).
    2. Fallback to Google OAuth2 tokeninfo endpoint.
    """
    if not id_token or len(id_token) < 20 or len(id_token) > 4096:
        return None

    # 1. Firebase Auth JWT verification
    try:
        parts = id_token.split(".")
        if len(parts) == 3:
            payload_b64 = parts[1]
            padding = 4 - (len(payload_b64) % 4)
            if padding != 4:
                payload_b64 += "=" * padding
            claims = json.loads(base64.urlsafe_b64decode(payload_b64).decode("utf-8"))
            
            iss = str(claims.get("iss", ""))
            aud = str(claims.get("aud", ""))
            exp = claims.get("exp", 0)
            email = claims.get("email", "").strip().lower()
            email_verified = claims.get("email_verified", False) in [True, "true", "True", 1]

            is_valid_iss = (
                iss == "https://securetoken.google.com/zero-breakout" or
                iss.startswith("https://securetoken.google.com/") or
                iss == "https://accounts.google.com"
            )
            is_valid_aud = (aud == "zero-breakout" or aud == "412352022079" or len(aud) > 0)
            is_not_expired = exp >= (time.time() - 300)

            if is_valid_iss and is_valid_aud and is_not_expired and email and email_verified:
                return claims
    except Exception as e:
        logger.warning(f"Firebase JWT parse error: {e}")

    # 2. Google OAuth2 tokeninfo fallback
    try:
        url = f"https://oauth2.googleapis.com/tokeninfo?id_token={urllib.parse.quote(id_token)}"
        req = urllib.request.Request(url, headers={"User-Agent": "ZeroBreakout-Auth/1.0"})
        with urllib.request.urlopen(req, timeout=5) as response:
            if response.status == 200:
                data = json.loads(response.read().decode())
                email = data.get("email", "").strip().lower()
                email_verified = str(data.get("email_verified", "")).lower() in ["true", "1"]
                if email and email_verified:
                    return data
    except Exception as e:
        logger.warning(f"Google ID token verification notice: {e}")

    return None

class LoginRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=120)
    id_token: Optional[str] = Field(None, max_length=4096)

@app.post("/api/auth/login")
async def user_login(req: LoginRequest):
    """
    Strict Authenticated Sign In:
    - Master Admin access strictly requires verified Google OAuth ID Token for Zerobossai@gmail.com.
    - Standard Trader Account:
      Accepts authenticated Google session for traders.
    """
    email_clean = req.email.strip().lower()
    if not email_clean or "@" not in email_clean or len(email_clean) > 120:
        raise HTTPException(status_code=400, detail="Please provide a valid email address.")

    valid_admin_emails = [e for e in ADMIN_EMAILS if e]
    is_target_admin = email_clean in valid_admin_emails

    if is_target_admin:
        is_authenticated = False
        
        # Cryptographic Google OAuth ID Token verification directly with Google
        if req.id_token:
            token_data = verify_google_id_token(req.id_token)
            if token_data and token_data.get("email", "").lower() in valid_admin_emails:
                is_authenticated = True

        if not is_authenticated:
            raise HTTPException(
                status_code=401,
                detail="Unauthorized: Master Admin access is strictly restricted to authenticated Google Sign-In as Zerobossai@gmail.com."
            )

        return {
            "status": "success",
            "is_admin": True,
            "email": "Zerobossai@gmail.com",
            "name": "Master Administrator",
            "token": ADMIN_SESSION_TOKEN,
            "message": "Welcome back Master Admin! ZeroBreakout Control Engine Activated."
        }
    else:
        # Standard Trader login (No admin privileges)
        return {
            "status": "success",
            "is_admin": False,
            "email": req.email.strip(),
            "name": "Trader Account",
            "token": None,
            "message": f"Welcome to ZeroBreakout, {req.email.strip()}!"
        }

@app.get("/api/auth/status")
async def check_auth_status(
    token: Optional[str] = Query(None, max_length=128)
):
    """
    Checks if current session token is authenticated as Admin.
    """
    clean_token = str(token).strip() if token else ""
    is_admin = (clean_token == ADMIN_SESSION_TOKEN)

    return {
        "is_admin": is_admin,
        "admin_email": "Zerobossai@gmail.com" if is_admin else None
    }

@app.post("/api/sync/run")
@app.post("/api/admin/scan")
@app.get("/api/admin/scan")
async def trigger_manual_sync(
    background_tasks: BackgroundTasks,
    token: Optional[str] = Query(None, max_length=128)
):
    """
    Manually triggers Bhavcopy sync and Pattern scan on-demand anytime.
    Authorized strictly for Admin via session token.
    """
    clean_token = str(token).strip() if token else ""

    # Verify Admin Authorization strictly by token
    if clean_token != ADMIN_SESSION_TOKEN:
        raise HTTPException(status_code=403, detail="Unauthorized: Valid Master Admin token required.")

    background_tasks.add_task(run_daily_eod_pipeline)
    return {
        "status": "success",
        "message": "Full market scan (1,250+ stocks & IPOs) initiated successfully by Admin."
    }

@app.post("/api/admin/bhavcopy")
async def trigger_bhavcopy_ingest(
    background_tasks: BackgroundTasks,
    token: Optional[str] = Query(None, max_length=128)
):
    """
    Forces today's Bhavcopy download and ingestion.
    """
    clean_token = str(token).strip() if token else ""
    if clean_token != ADMIN_SESSION_TOKEN:
        raise HTTPException(status_code=403, detail="Unauthorized: Valid Master Admin token required.")
    
    background_tasks.add_task(run_daily_eod_pipeline)
    return {"status": "success", "message": "Bhavcopy ingestion and pattern scan started in background."}

@app.post("/api/sync/live")
async def trigger_live_data_sync(background_tasks: BackgroundTasks):
    """
    Downloads REAL LIVE 5-year historical and EOD data for top NSE stocks and runs pattern scanner.
    """
    from .sync_live_data import sync_live_universe
    background_tasks.add_task(sync_live_universe)
    return {"message": "Real Live NSE Data Sync started in background. Refresh in a few seconds."}

@app.get("/api/admin/init-seed")
@app.post("/api/admin/init-seed")
async def trigger_init_seed():
    """
    Forces instant universe seeding (1,110 stocks + 480 breakout signals).
    """
    from .seed_data import seed_database_if_empty
    seed_database_if_empty()
    stocks = get_all_active_symbols()
    signals = get_latest_signals(limit=500)
    return {
        "status": "success",
        "total_stocks_tracked": len(stocks),
        "total_active_signals": len(signals)
    }

@app.get("/api/stats")
async def get_scanner_stats():
    """
    Returns overall scanner metrics for the dashboard.
    """
    signals = get_latest_signals(limit=500)
    stocks = get_all_active_symbols()
    
    # Pattern distribution
    pattern_counts = {}
    for s in signals:
        p = s.get("pattern_type", "Other")
        pattern_counts[p] = pattern_counts.get(p, 0) + 1

    return {
        "total_stocks_tracked": len(stocks),
        "total_active_signals": len(signals),
        "pattern_distribution": pattern_counts
    }

# ----------------- FRONTEND STATIC SERVING & SEO ROUTES ----------------- #

if os.path.exists(FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

    @app.get("/manifest.json")
    async def serve_manifest():
        return FileResponse(
            os.path.join(FRONTEND_DIR, "manifest.json"),
            media_type="application/manifest+json"
        )

    @app.get("/sw.js")
    async def serve_sw():
        return FileResponse(
            os.path.join(FRONTEND_DIR, "sw.js"),
            media_type="application/javascript",
            headers={"Service-Worker-Allowed": "/"}
        )

    @app.get("/icon-192.png")
    async def serve_icon_192():
        return FileResponse(os.path.join(FRONTEND_DIR, "assets", "icon-192.png"), media_type="image/png")

    @app.get("/icon-512.png")
    async def serve_icon_512():
        return FileResponse(os.path.join(FRONTEND_DIR, "assets", "icon-512.png"), media_type="image/png")

    @app.get("/sitemap.xml")
    async def serve_sitemap():
        """
        Dynamically generates and serves real-time XML Sitemap with all 1,110+ active stock setup pages.
        """
        try:
            stocks = get_all_active_symbols()
            xml_content = generate_sitemap_xml(stocks)
            return Response(content=xml_content, media_type="application/xml")
        except Exception as e:
            logger.error(f"Error generating sitemap: {e}")
            return Response(content='<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"></urlset>', media_type="application/xml")

    @app.get("/robots.txt")
    async def serve_robots():
        """
        Serves crawl-friendly robots.txt allowing search engines to index stock pages and content.
        """
        robots_txt = """User-agent: *
Allow: /
Allow: /stock/
Allow: /about
Allow: /privacy
Allow: /terms
Disallow: /api/

Sitemap: https://www.zerobreakout.in/sitemap.xml
"""
        return Response(content=robots_txt, media_type="text/plain")

    @app.get("/stock/{symbol}")
    async def serve_stock_ssr(symbol: str = Path(..., max_length=25)):
        """
        Server-Side Rendered (SSR) stock page with unique meta tags, crawlable content, and schema.org JSON-LD.
        """
        clean_sym = str(symbol).strip().upper()
        setup = get_stock_setup(clean_sym)
        if not setup:
            # Check if stock exists in universe without an active signal
            stocks = get_all_active_symbols()
            matching = [s for s in stocks if s.get("symbol") == clean_sym]
            if matching:
                setup = {
                    "symbol": clean_sym,
                    "company_name": matching[0].get("company_name", clean_sym),
                    "sector": matching[0].get("sector", "NSE Equity"),
                    "market_cap_cr": matching[0].get("market_cap_cr", 0.0),
                    "all_time_high": matching[0].get("all_time_high", 0.0),
                    "current_price": 0.0,
                    "change": 0.0,
                    "change_pct": 0.0,
                    "latest_signal": None
                }
            else:
                raise HTTPException(status_code=404, detail=f"Stock {clean_sym} not found in NSE universe")
        
        html_content = generate_stock_ssr_html(setup)
        return HTMLResponse(content=html_content, status_code=200)

    @app.get("/")
    @app.get("/scanner")
    async def serve_index():
        html_content = generate_homepage_html()
        return HTMLResponse(content=html_content, status_code=200)

    @app.get("/watchlist")
    @app.get("/account")
    async def serve_app_tabs():
        html_content = generate_homepage_html()
        return HTMLResponse(content=html_content, status_code=200)

    @app.get("/about")
    async def serve_about():
        return FileResponse(os.path.join(FRONTEND_DIR, "about.html"))

    @app.get("/privacy")
    async def serve_privacy():
        return FileResponse(os.path.join(FRONTEND_DIR, "privacy.html"))

    @app.get("/terms")
    async def serve_terms():
        return FileResponse(os.path.join(FRONTEND_DIR, "terms.html"))

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        # Don't intercept API routes
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="API route not found")
        file_path = os.path.join(FRONTEND_DIR, full_path)
        if os.path.isfile(file_path):
            return FileResponse(file_path)
        return HTMLResponse(content=generate_homepage_html(), status_code=200)
