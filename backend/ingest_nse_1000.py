import os
import sys
import io
import time
import logging
import requests
import pandas as pd
from datetime import datetime
from typing import List, Dict, Any

from .database import (
    init_db,
    get_connection,
    upsert_stock,
    upsert_price_batch,
    update_stock_ath_from_history
)
from .patterns.engine import pattern_engine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("ZeroBreakout.NSE1000Ingest")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
}

def get_official_nse_1000_symbols() -> List[Dict[str, str]]:
    """
    Fetches the complete official list of NSE-listed equities from NSE India.
    Returns list of dicts with symbol, name, and ticker.
    """
    url = "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv"
    stocks = []
    
    try:
        logger.info("Fetching official equity scrip master from NSE archives...")
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code == 200:
            df = pd.read_csv(io.StringIO(resp.text))
            # Clean column names
            df.columns = [c.strip() for c in df.columns]
            
            # Filter for EQ series
            if "SERIES" in df.columns:
                df = df[df["SERIES"].str.strip() == "EQ"]

            for _, row in df.iterrows():
                sym = str(row.get("SYMBOL", "")).strip().upper()
                name = str(row.get("NAME OF COMPANY", sym)).strip()
                if sym:
                    stocks.append({
                        "symbol": sym,
                        "ticker": f"{sym}.NS",
                        "name": name,
                        "sector": "NSE Equity"
                    })
            logger.info(f"Loaded {len(stocks)} official NSE EQ companies from NSE archives.")
            return stocks[:1000]
    except Exception as e:
        logger.warning(f"Failed to fetch EQUITY_L.csv directly: {e}")

    # Fallback to predefined top universe if NSE connection fails
    from .sync_live_data import NSE_UNIVERSE
    return [{"symbol": s["symbol"], "ticker": f"{s['symbol']}.NS", "name": s["name"], "sector": s.get("sector", "NSE Equity")} for s in NSE_UNIVERSE]

def ingest_top_nse_1000(limit: int = 1000, chunk_size: int = 50):
    """
    Downloads historical OHLCV data for top 1000 NSE companies in parallel batches,
    updates database, and triggers pattern scan.
    """
    import yfinance as yf

    init_db()
    stocks = get_official_nse_1000_symbols()
    stocks = stocks[:limit]
    
    logger.info(f"Starting ingestion pipeline for {len(stocks)} NSE companies in chunks of {chunk_size}...")

    total_synced_stocks = 0
    total_candles_saved = 0

    for i in range(0, len(stocks), chunk_size):
        chunk = stocks[i:i + chunk_size]
        tickers_list = [item["ticker"] for item in chunk]
        ticker_meta = {item["ticker"]: item for item in chunk}

        logger.info(f"[{i+1}-{min(i+chunk_size, len(stocks))}/{len(stocks)}] Downloading data for {len(chunk)} stocks...")

        try:
            data = yf.download(tickers_list, period="max", group_by="ticker", threads=True, progress=False)
        except Exception as e:
            logger.error(f"Error downloading chunk: {e}")
            continue

        if data is None or data.empty:
            continue

        for ticker in tickers_list:
            meta = ticker_meta[ticker]
            sym = meta["symbol"]

            try:
                if ticker in data.columns.levels[0]:
                    df_t = data[ticker].dropna(subset=["Close"]).copy()
                else:
                    continue

                if df_t.empty or len(df_t) < 10:
                    continue

                price_rows = []
                for dt, row in df_t.iterrows():
                    date_str = dt.strftime("%Y-%m-%d")
                    o = round(float(row["Open"]), 2)
                    h = round(float(row["High"]), 2)
                    l = round(float(row["Low"]), 2)
                    c = round(float(row["Close"]), 2)
                    v = int(row.get("Volume", 0) or 0)
                    price_rows.append((sym, date_str, o, h, l, c, v))

                if not price_rows:
                    continue

                # Calculate real ATH
                all_highs = [p[3] for p in price_rows]
                real_ath = float(max(all_highs))
                ath_idx = all_highs.index(real_ath)
                ath_date = price_rows[ath_idx][1]

                # Upsert stock metadata
                upsert_stock(
                    symbol=sym,
                    company_name=meta["name"],
                    sector=meta["sector"],
                    market_cap_cr=0,
                    all_time_high=real_ath,
                    ath_date=ath_date
                )

                # Batch insert price rows
                upsert_price_batch(price_rows)
                total_synced_stocks += 1
                total_candles_saved += len(price_rows)

            except Exception as item_err:
                continue

        logger.info(f"Progress: {total_synced_stocks} stocks successfully saved so far ({total_candles_saved} candles).")
        # Politeness sleep between batch downloads
        time.sleep(0.5)

    logger.info(f"Bulk ingestion complete: {total_synced_stocks} NSE companies loaded.")
    
    # Run Pattern Scan across all 1000 stocks!
    logger.info("Running technical pattern detection scan across all 1000 stocks...")
    scan_results = pattern_engine.scan_all_stocks()
    logger.info(f"Pattern Scan Complete! Results: {scan_results}")
    return {
        "stocks_synced": total_synced_stocks,
        "total_candles": total_candles_saved,
        "scan_results": scan_results
    }

if __name__ == "__main__":
    ingest_top_nse_1000(limit=1000, chunk_size=50)
