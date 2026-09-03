import os
import io
import zipfile
import requests
import logging
from datetime import datetime, timedelta
import pandas as pd
from typing import List, Dict, Any, Optional
from .database import upsert_price_batch, upsert_stock, update_stock_ath_from_history

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

    # Handle various column namings in NSE files (All UPPERCASE)
    col_map = {
        "SYMBOL": "symbol",
        "TCKRSYMB": "symbol",
        "SECURITY": "symbol",
        "OPEN": "open",
        "OPEN_PRICE": "open",
        "OPNPRIC": "open",
        "HIGH": "high",
        "HIGH_PRICE": "high",
        "HGHPRIC": "high",
        "LOW": "low",
        "LOW_PRICE": "low",
        "LWPRIC": "low",
        "CLOSE": "close",
        "CLOSE_PRICE": "close",
        "CLSPRIC": "close",
        "LAST_PRICE": "close",
        "LASTPRIC": "close",
        "TOTTRDQTY": "volume",
        "TOTAL_TRADED_QTY": "volume",
        "TTLTRADGVOL": "volume",
        "SERIES": "series",
        "SCTYSRS": "series"
    }

    df_clean = df.rename(columns=col_map)
    
    # Filter for Equity Series (EQ / BE)
    if "series" in df_clean.columns:
        df_clean = df_clean[df_clean["series"].astype(str).str.strip().isin(["EQ", "BE"])]

    required_cols = ["symbol", "open", "high", "low", "close", "volume"]
    missing = [c for c in required_cols if c not in df_clean.columns]
    if missing:
        logger.error(f"Missing required columns in Bhavcopy: {missing}")
        return 0

    price_rows = []
    for _, row in df_clean.iterrows():
        try:
            sym = str(row["symbol"]).strip().upper()
            o = float(row["open"])
            h = float(row["high"])
            l = float(row["low"])
            c = float(row["close"])
            v = int(row["volume"])
            price_rows.append((sym, target_date_str, o, h, l, c, v))
        except (ValueError, TypeError):
            continue

    if price_rows:
        # Upsert stock metadata first to satisfy foreign key constraints
        for sym, _, _, h, _, _, _ in price_rows:
            upsert_stock(sym, sym, "General", 0, h, target_date_str)

        # Batch insert price records
        upsert_price_batch(price_rows)
        logger.info(f"Saved {len(price_rows)} price records for {target_date_str}")

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
