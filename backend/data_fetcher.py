import os
import io
import zipfile
import requests
import logging
from datetime import datetime, timedelta, timezone
import pandas as pd
from typing import List, Dict, Any, Optional
from .database import upsert_price_batch, upsert_stock, update_stock_ath_from_history, get_connection

logger = logging.getLogger("ZeroBreakout.DataFetcher")

NSE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/"
}

def fetch_nse_bhavcopy_for_date(target_date: datetime) -> Optional[pd.DataFrame]:
    """
    Downloads and parses NSE Daily Bhavcopy for a given date.
    Supports both modern BhavCopy_NSE_CM format and classic sec_bhavdata format.
    """
    date_str_cm = target_date.strftime("%Y%m%d")
    date_str_classic = target_date.strftime("%d%m%Y")
    date_str_old = target_date.strftime("%d%b%Y").upper()

    urls_to_try = [
        f"https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_{date_str_cm}_F_0000.csv.zip",
        f"https://archives.nseindia.com/products/content/sec_bhavdata_full_{date_str_classic}.csv",
        f"https://archives.nseindia.com/content/historical/EQUITIES/{target_date.year}/{target_date.strftime('%b').upper()}/cm{date_str_old}bhav.csv.zip"
    ]

    session = requests.Session()
    session.headers.update(NSE_HEADERS)

    for url in urls_to_try:
        try:
            logger.info(f"Attempting to download Bhavcopy from: {url}")
            resp = session.get(url, timeout=15)
            if resp.status_code == 200:
                content = resp.content
                if url.endswith(".zip"):
                    with zipfile.ZipFile(io.BytesIO(content)) as z:
                        csv_filename = z.namelist()[0]
                        with z.open(csv_filename) as f:
                            df = pd.read_csv(f)
                else:
                    df = pd.read_csv(io.BytesIO(content))

                # Clean column headers
                df.columns = [c.strip().upper() for c in df.columns]
                logger.info(f"Successfully downloaded Bhavcopy with {len(df)} rows for {target_date.strftime('%Y-%m-%d')}")
                return df
        except Exception as e:
            logger.warning(f"Could not fetch Bhavcopy from {url}: {e}")

    return None

def process_and_save_bhavcopy(df: pd.DataFrame, target_date_str: str) -> int:
    """
    Parses normalized Bhavcopy DataFrame and saves to price_history and stocks tables.
    """
    if df is None or df.empty:
        return 0

    # Ensure clean column names (strip whitespace and uppercase)
    df = df.copy()
    df.columns = [str(c).strip().upper() for c in df.columns]

    # Handle standard NSE column names
    col_map = {
        "TCKRSYMB": "symbol",
        "SYMBOL": "symbol",
        "SECURITY": "symbol",
        "OPNPRIC": "open",
        "OPEN_PRICE": "open",
        "OPEN": "open",
        "HGHPRIC": "high",
        "HIGH_PRICE": "high",
        "HIGH": "high",
        "LWPRIC": "low",
        "LOW_PRICE": "low",
        "LOW": "low",
        "CLSPRIC": "close",
        "CLOSE_PRICE": "close",
        "CLOSE": "close",
        "TTLTRADGVOL": "volume",
        "TOTTRDQTY": "volume",
        "TOTAL_TRADED_QTY": "volume",
        "TTL_TRD_QNTY": "volume",
        "SCTYSRS": "series",
        "SERIES": "series"
    }

    # Map only columns that exist
    rename_dict = {}
    used_targets = set()
    for col in df.columns:
        if col in col_map:
            target = col_map[col]
            if target not in used_targets:
                rename_dict[col] = target
                used_targets.add(target)

    df_clean = df.rename(columns=rename_dict)
    # Deduplicate columns if any duplicate slipped through
    df_clean = df_clean.loc[:, ~df_clean.columns.duplicated()]

    # Filter for Equity Series (EQ / BE / SM / ST)
    if "series" in df_clean.columns:
        df_clean = df_clean[df_clean["series"].astype(str).str.strip().isin(["EQ", "BE", "SM", "ST"])]

    required_cols = ["symbol", "open", "high", "low", "close", "volume"]
    missing = [c for c in required_cols if c not in df_clean.columns]
    if missing:
        logger.error(f"Missing required columns in Bhavcopy: {missing}")
        return 0

    price_rows = []
    for _, row in df_clean.iterrows():
        try:
            sym = str(row["symbol"]).strip().upper()
            if not sym or sym == "NAN":
                continue
            o = float(row["open"])
            h = float(row["high"])
            l = float(row["low"])
            c = float(row["close"])
            v = int(row["volume"])
            price_rows.append((sym, target_date_str, o, h, l, c, v))
        except (ValueError, TypeError):
            continue

    if price_rows:
        conn = get_connection()
        now_str = datetime.now().isoformat()
        with conn:
            # 1. Fast Batch Upsert stocks to satisfy foreign keys & update ATH
            stock_tuples = [(sym, sym, "General", 0, h, target_date_str, now_str) for sym, _, _, h, _, _, _ in price_rows]
            conn.executemany("""
                INSERT INTO stocks (symbol, company_name, sector, market_cap_cr, all_time_high, ath_date, is_active, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, 1, ?)
                ON CONFLICT(symbol) DO UPDATE SET
                    all_time_high=CASE WHEN excluded.all_time_high > stocks.all_time_high THEN excluded.all_time_high ELSE stocks.all_time_high END,
                    ath_date=CASE WHEN excluded.all_time_high > stocks.all_time_high THEN excluded.ath_date ELSE stocks.ath_date END,
                    updated_at=excluded.updated_at;
            """, stock_tuples)

            # 2. Fast Batch Upsert price records
            conn.executemany("""
                INSERT INTO price_history (symbol, date, open, high, low, close, volume)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(symbol, date) DO UPDATE SET
                    open=excluded.open,
                    high=excluded.high,
                    low=excluded.low,
                    close=excluded.close,
                    volume=excluded.volume;
            """, price_rows)
        conn.close()
        logger.info(f"Successfully saved {len(price_rows)} price records for {target_date_str}")

    return len(price_rows)

def fetch_yahoo_eod_history(symbol: str, years: int = 5) -> Optional[pd.DataFrame]:
    """
    Free fallback data fetcher for historical 5-year OHLCV for NSE stocks using Yahoo Finance.
    Appends .NS suffix for NSE symbols.
    """
    nse_sym = f"{symbol.upper()}.NS" if not symbol.endswith(".NS") else symbol.upper()
    try:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=years * 365 + 30)
        
        # We can use yfinance if available, else direct query
        try:
            import yfinance as yf
            ticker = yf.Ticker(nse_sym)
            df = ticker.history(start=start_date.strftime("%Y-%m-%d"), end=end_date.strftime("%Y-%m-%d"))
            if not df.empty:
                df = df.reset_index()
                df.columns = [c.lower() for c in df.columns]
                # format date column
                if "date" in df.columns:
                    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
                return df[["date", "open", "high", "low", "close", "volume"]]
        except Exception as yf_err:
            logger.debug(f"yfinance lookup error for {symbol}: {yf_err}")

        # Fallback to direct Yahoo Finance query
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{nse_sym}?range={years}y&interval=1d"
        resp = requests.get(url, headers=NSE_HEADERS, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            result = data.get("chart", {}).get("result", [])
            if result:
                res = result[0]
                timestamps = res.get("timestamp", [])
                quote = res.get("indicators", {}).get("quote", [{}])[0]
                opens = quote.get("open", [])
                highs = quote.get("high", [])
                lows = quote.get("low", [])
                closes = quote.get("close", [])
                volumes = quote.get("volume", [])

                rows = []
                for i in range(len(timestamps)):
                    if opens[i] is not None and closes[i] is not None:
                        d_str = datetime.fromtimestamp(timestamps[i]).strftime("%Y-%m-%d")
                        rows.append({
                            "date": d_str,
                            "open": round(float(opens[i]), 2),
                            "high": round(float(highs[i]), 2),
                            "low": round(float(lows[i]), 2),
                            "close": round(float(closes[i]), 2),
                            "volume": int(volumes[i] or 0)
                        })
                if rows:
                    return pd.DataFrame(rows)
    except Exception as e:
        logger.warning(f"Failed to fetch Yahoo history for {symbol}: {e}")
    return None

def sync_stock_5year_history(symbol: str, company_name: str, sector: str, market_cap_cr: float, ath: float = 0):
    """
    Synchronizes 5-year OHLCV for a single stock and calculates ATH.
    """
    df = fetch_yahoo_eod_history(symbol, years=5)
    if df is not None and not df.empty:
        records = [
            (symbol.upper(), row["date"], row["open"], row["high"], row["low"], row["close"], row["volume"])
            for _, row in df.iterrows()
        ]
        upsert_price_batch(records)
        
        max_high = float(df["high"].max())
        ath_val = max(max_high, ath)
        ath_row = df[df["high"] == max_high].iloc[-1]
        ath_date = str(ath_row["date"])
        
        upsert_stock(symbol.upper(), company_name, sector, market_cap_cr, ath_val, ath_date)
        logger.info(f"Synced {len(records)} daily candles for {symbol} (ATH: ₹{ath_val:.2f})")
    else:
        upsert_stock(symbol.upper(), company_name, sector, market_cap_cr, ath, None)

def sync_missing_bhavcopies() -> Dict[str, Any]:
    """
    Automatic Multi-Day Catch-Up Engine:
    Detects any missing trading sessions between the newest price_history date and current IST date/time.
    Downloads all missing Bhavcopies chronologically, ingests them into the database, updates ATHs,
    and runs the pattern detection scanner across the entire universe.
    """
    from .patterns.engine import pattern_engine

    ist_now = datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)
    logger.info(f"Checking for missing Bhavcopies. Current IST Time: {ist_now.strftime('%Y-%m-%d %H:%M:%S (%A)')}")

    # Determine latest target date
    # If weekday and before 16:15 IST, market is still active or Bhavcopy not yet ready, so target up to yesterday
    if ist_now.weekday() < 5 and (ist_now.hour < 16 or (ist_now.hour == 16 and ist_now.minute < 15)):
        target_end = ist_now - timedelta(days=1)
    else:
        target_end = ist_now

    conn = get_connection()
    row = conn.execute("SELECT MAX(date) as max_date FROM price_history").fetchone()
    last_db_date_str = row["max_date"] if row and row["max_date"] else None
    
    if not last_db_date_str:
        last_db_date = target_end - timedelta(days=30)
    else:
        last_db_date = datetime.strptime(last_db_date_str, "%Y-%m-%d")

    logger.info(f"Latest database market date: {last_db_date.strftime('%Y-%m-%d')}. Target date: {target_end.strftime('%Y-%m-%d')}")

    # Generate candidate trading days (Mon-Fri)
    curr = last_db_date + timedelta(days=1)
    dates_to_check = []
    while curr.date() <= target_end.date():
        if curr.weekday() < 5:  # Mon=0, Fri=4
            dates_to_check.append(curr)
        curr += timedelta(days=1)

    if not dates_to_check:
        logger.info("Database is already up to date with the latest NSE trading session.")
        conn.close()
        return {"status": "up_to_date", "synced_days": 0, "message": "Already up to date."}

    logger.info(f"Identified {len(dates_to_check)} candidate trading days to verify: {[d.strftime('%Y-%m-%d') for d in dates_to_check]}")

    synced_days = 0
    total_candles_added = 0

    for d in dates_to_check:
        d_str = d.strftime("%Y-%m-%d")
        existing_cnt = conn.execute("SELECT COUNT(DISTINCT symbol) as cnt FROM price_history WHERE date = ?", (d_str,)).fetchone()["cnt"]
        if existing_cnt >= 500:
            logger.info(f"[{d_str}] Already loaded ({existing_cnt} stocks). Skipping.")
            continue

        logger.info(f"[{d_str}] Missing from DB. Downloading Bhavcopy from NSE...")
        df = fetch_nse_bhavcopy_for_date(d)
        if df is not None and not df.empty:
            saved = process_and_save_bhavcopy(df, d_str)
            logger.info(f"[{d_str}] Successfully saved {saved} stock records.")
            if saved > 0:
                synced_days += 1
                total_candles_added += saved
        else:
            logger.info(f"[{d_str}] No Bhavcopy available (likely market holiday or weekend).")

    conn.close()

    scan_results = None
    if synced_days > 0:
        logger.info(f"Catch-up complete: Ingested {synced_days} trading days ({total_candles_added} candles). Triggering pattern engine scan...")
        scan_results = pattern_engine.scan_all_stocks()
        logger.info(f"Pattern Engine Scan complete: {scan_results}")

    return {
        "status": "success",
        "synced_days": synced_days,
        "candles_added": total_candles_added,
        "scan_results": scan_results
    }

