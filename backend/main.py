import os
import logging
from typing import Optional, List, Dict, Any
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Query, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
import pandas as pd

from .database import (
    init_db,
    get_latest_signals,
    get_stock_setup,
    get_stock_price_history,
    get_watchlist,
    toggle_watchlist,
    is_in_watchlist,
    get_all_active_symbols
)
from .seed_data import seed_database_if_empty
from .scheduler import start_scheduler, stop_scheduler, run_daily_eod_pipeline
from .gemini_service import get_gemini_analysis

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
    yield
    # Shutdown: stop scheduler cleanly
    stop_scheduler()

app = FastAPI(
    title="ZeroBreakout API",
    description="Stock Pattern Scanner for NSE-listed Indian stocks",
    version="1.0.0",
    lifespan=lifespan
)

# Enable CORS for local dev and production
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def handle_uptime_head_requests(request, call_next):
    if request.method == "HEAD":
        from starlette.responses import Response
        return Response(status_code=200)
    return await call_next(request)

FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend")

# ----------------- HEALTH & UPTIME MONITOR ENDPOINTS ----------------- #

@app.get("/health")
@app.head("/health")
@app.head("/")
async def health_check():
    return {"status": "ok", "app": "ZeroBreakout Terminal", "timestamp": datetime.utcnow().isoformat()}

# ----------------- API ENDPOINTS ----------------- #

@app.get("/api/signals")
async def get_signals(
    pattern: Optional[str] = Query(None, description="Filter by pattern type or 'all'"),
    search: Optional[str] = Query(None, description="Search by symbol or company name"),
    limit: int = Query(150, ge=1, le=500)
):
    """
    Returns precomputed signals from the signals table.
    No pattern computation on page load — instantaneous response!
    """
    try:
        signals = get_latest_signals(pattern_type=pattern, search_query=search, limit=limit)
        return {"count": len(signals), "signals": signals}
    except Exception as e:
        logger.error(f"Error fetching signals: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/stocks/{symbol}/setup")
async def get_stock_setup_data(symbol: str):
    """
    Fetches stock metadata, current price, day change, active pattern signal, and watchlist state.
    """
    setup = get_stock_setup(symbol)
    if not setup:
        raise HTTPException(status_code=404, detail=f"Stock {symbol.upper()} not found")
    
    setup["in_watchlist"] = is_in_watchlist(symbol)
    return setup

@app.get("/api/stocks/{symbol}/history")
async def get_stock_history_data(
    symbol: str,
    range: str = Query("1Y", pattern="^(1M|6M|1Y|5Y|10Y|ALL)$")
):
    """
    Returns OHLCV candlestick data and overlaid moving averages (20 SMA & 50 SMA).
    """
    days_map = {
        "1M": 25,
        "6M": 130,
        "1Y": 252,
        "5Y": 1250,
        "10Y": 2500,
        "ALL": 2500
    }
    limit_days = days_map.get(range, 252)
    history = get_stock_price_history(symbol, limit_days=limit_days + 50) # extra for SMA calc

    # On-demand multi-year history auto-fetch if database has less than requested history
    if (len(history) < min(limit_days, 500) and range in ["5Y", "10Y", "ALL"]) or not history:
        try:
            import yf_auto
        except ImportError:
            pass
        try:
            import yfinance as yf
            from backend.database import upsert_price_batch, update_stock_ath_from_history
            tk = yf.Ticker(f"{symbol.upper()}.NS")
            df_yf = tk.history(period="10y")
            if not df_yf.empty:
                df_yf = df_yf.reset_index()
                date_col = "Date" if "Date" in df_yf.columns else df_yf.columns[0]
                df_yf["date"] = pd.to_datetime(df_yf[date_col]).dt.strftime("%Y-%m-%d")
                candles_to_save = []
                for _, r in df_yf.iterrows():
                    candles_to_save.append((
                        symbol.upper(),
                        r["date"],
                        float(r["Open"]),
                        float(r["High"]),
                        float(r["Low"]),
                        float(r["Close"]),
                        int(r["Volume"])
                    ))
                if candles_to_save:
                    upsert_price_batch(candles_to_save)
                    update_stock_ath_from_history(symbol.upper())
                    history = get_stock_price_history(symbol, limit_days=limit_days + 50)
        except Exception:
            pass
    
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
async def get_stock_ai_analysis(symbol: str):
    """
    Generates AI-powered technical pattern breakdown using Gemini API.
    """
    setup = get_stock_setup(symbol)
    if not setup:
        raise HTTPException(status_code=404, detail=f"Stock {symbol.upper()} not found")

    signal = setup.get("latest_signal")
    analysis = get_gemini_analysis(symbol, setup, signal)
    return analysis

@app.get("/api/watchlist")
async def get_user_watchlist():
    """
    Returns list of starred stocks with live stats.
    """
    items = get_watchlist(user_id="default_user")
    return {"count": len(items), "items": items}

@app.post("/api/watchlist/{symbol}")
async def toggle_stock_watchlist(symbol: str):
    """
    Toggles watchlist state for a stock.
    """
    is_added = toggle_watchlist(symbol, user_id="default_user")
    return {"symbol": symbol.upper(), "in_watchlist": is_added}

ADMIN_EMAILS = [
    "zerobossai@gmail.com",
    "zerobossai@gamil.com",
    os.environ.get("ADMIN_EMAIL", "").strip().lower()
]

ADMIN_SESSION_TOKEN = os.environ.get("ADMIN_SESSION_TOKEN", "zb_admin_token_zerobossai_8899")

from pydantic import BaseModel

class LoginRequest(BaseModel):
    email: str
    password: Optional[str] = None

@app.post("/api/auth/login")
async def user_login(req: LoginRequest):
    """
    Universal Sign In:
    - If email is Zerobossai@gmail.com -> Grants full Admin privileges.
    - If email is any trader's email -> Grants Trader Account access.
    """
    email_clean = req.email.strip().lower()
    if not email_clean or "@" not in email_clean:
        raise HTTPException(status_code=400, detail="Please provide a valid email address.")

    if email_clean in [e for e in ADMIN_EMAILS if e]:
        return {
            "status": "success",
            "is_admin": True,
            "email": "Zerobossai@gmail.com",
            "name": "Master Administrator",
            "token": ADMIN_SESSION_TOKEN,
            "message": "Welcome back Master Admin! ZeroBreakout Control Engine Activated."
        }
    else:
        return {
            "status": "success",
            "is_admin": False,
            "email": req.email.strip(),
            "name": "Trader Account",
            "token": None,
            "message": f"Welcome to ZeroBreakout, {req.email.strip()}!"
        }

@app.get("/api/auth/status")
async def check_auth_status(token: Optional[str] = None, email: Optional[str] = None):
    """
    Checks if current session is authenticated as Admin.
    """
    is_admin = False
    if token == ADMIN_SESSION_TOKEN:
        is_admin = True
    elif email and email.strip().lower() in [e for e in ADMIN_EMAILS if e]:
        is_admin = True

    return {
        "is_admin": is_admin,
        "admin_email": "Zerobossai@gmail.com" if is_admin else None
    }

@app.post("/api/sync/run")
@app.post("/api/admin/scan")
@app.get("/api/admin/scan")
async def trigger_manual_sync(background_tasks: BackgroundTasks, token: Optional[str] = None, email: Optional[str] = None):
    """
    Manually triggers Bhavcopy sync and Pattern scan on-demand anytime.
    Authorized for Admin (Zerobossai@gmail.com).
    """
    # Verify Admin Authorization
    is_auth = False
    if token == ADMIN_SESSION_TOKEN or (email and email.strip().lower() in [e for e in ADMIN_EMAILS if e]):
        is_auth = True
    elif not os.environ.get("PRODUCTION"): # Allow local dev
        is_auth = True

    if not is_auth:
        raise HTTPException(status_code=403, detail="Unauthorized: Please log in with Zerobossai@gmail.com to trigger scans.")

    background_tasks.add_task(run_daily_eod_pipeline)
    return {
        "status": "success",
        "message": "Full market scan (1,250+ stocks & IPOs) initiated successfully by Admin."
    }

@app.post("/api/admin/bhavcopy")
async def trigger_bhavcopy_ingest(background_tasks: BackgroundTasks, token: Optional[str] = None):
    """
    Forces today's Bhavcopy download and ingestion.
    """
    if token != ADMIN_SESSION_TOKEN and os.environ.get("PRODUCTION"):
        raise HTTPException(status_code=403, detail="Unauthorized.")
    
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

# ----------------- FRONTEND STATIC SERVING ----------------- #

if os.path.exists(FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

    @app.get("/")
    async def serve_index():
        return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        # Don't intercept API routes
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="API route not found")
        file_path = os.path.join(FRONTEND_DIR, full_path)
        if os.path.isfile(file_path):
            return FileResponse(file_path)
        return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))
