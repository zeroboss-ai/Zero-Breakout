import os
import sys
import io
import time
import logging
import requests
import datetime
import pandas as pd
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
logger = logging.getLogger("ZeroBreakout.MainboardIPOIngest")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
}

def fetch_all_mainboard_ipos_last_year() -> List[Dict[str, Any]]:
    """
    Fetches official NSE equity list and filters STRICTLY for:
    1. SERIES == 'EQ' (Mainboard Equities ONLY - No SME)
    2. DATE OF LISTING within the last 1 year (>= 365 days ago)
    """
    url = "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv"
    ipos = []

    try:
        logger.info("Fetching official equity scrip master from NSE archives...")
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code == 200:
            df = pd.read_csv(io.StringIO(resp.text))
            df.columns = [c.strip() for c in df.columns]

            # 1. Strictly Mainboard Equity series only (Exclude SME series like SM, ST, etc.)
            if "SERIES" in df.columns:
                df = df[df["SERIES"].str.strip() == "EQ"].copy()

            # 2. Date of listing within last 1 year (365 days)
            if "DATE OF LISTING" in df.columns:
                df["LISTING_DT"] = pd.to_datetime(df["DATE OF LISTING"], format="%d-%b-%Y", errors="coerce")
                one_year_ago = datetime.datetime.now() - datetime.timedelta(days=365)
                df_ipo = df[df["LISTING_DT"] >= one_year_ago]
            else:
                df_ipo = df

            for _, row in df_ipo.iterrows():
                sym = str(row.get("SYMBOL", "")).strip().upper()
                name = str(row.get("NAME OF COMPANY", sym)).strip()
                list_dt = str(row.get("DATE OF LISTING", "")).strip()
                if sym:
                    ipos.append({
                        "symbol": sym,
                        "ticker": f"{sym}.NS",
                        "name": name,
                        "listing_date": list_dt,
                        "sector": "Mainboard IPO"
                    })
            
            logger.info(f"Identified {len(ipos)} official Mainboard IPOs listed on NSE in the last 1 year.")
            return ipos
    except Exception as e:
        logger.error(f"Error fetching official NSE IPO master: {e}")

    return []

def ingest_and_scan_mainboard_ipos(chunk_size: int = 50):
    """
    Downloads complete listing history for all Mainboard IPOs,
    updates database, and scans for IPO All-Time High Breakouts.
    """
    import yfinance as yf

    init_db()
    ipos = fetch_all_mainboard_ipos_last_year()
    if not ipos:
        logger.warning("No Mainboard IPOs identified.")
        return

    logger.info(f"Downloading listing history for all {len(ipos)} Mainboard IPOs in chunks of {chunk_size}...")

    total_synced = 0
    total_candles = 0

    for i in range(0, len(ipos), chunk_size):
        chunk = ipos[i:i + chunk_size]
        tickers_list = [item["ticker"] for item in chunk]
        ticker_meta = {item["ticker"]: item for item in chunk}

        logger.info(f"[{i+1}-{min(i+chunk_size, len(ipos))}/{len(ipos)}] Downloading IPO candles...")

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

                if df_t.empty or len(df_t) < 5:
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

                # Calculate True Lifetime ATH since IPO
                all_highs = [p[3] for p in price_rows]
                real_ath = float(max(all_highs))
                ath_idx = all_highs.index(real_ath)
                ath_date = price_rows[ath_idx][1]

                # Upsert stock metadata
                upsert_stock(
                    symbol=sym,
                    company_name=meta["name"],
                    sector=f"Mainboard IPO (Listed {meta['listing_date']})",
                    market_cap_cr=0,
                    all_time_high=real_ath,
                    ath_date=ath_date
                )

                # Batch insert price rows
                upsert_price_batch(price_rows)
                total_synced += 1
                total_candles += len(price_rows)

            except Exception as item_err:
                continue

        logger.info(f"IPO Progress: {total_synced} Mainboard IPOs saved ({total_candles} candles).")
        time.sleep(0.5)

    logger.info(f"Finished ingesting {total_synced} Mainboard IPOs.")

    # Trigger pattern scan across all stocks including the newly added IPOs!
    logger.info("Executing technical pattern detection across all stocks and IPOs...")
    scan_results = pattern_engine.scan_all_stocks()
    logger.info(f"Scan complete: {scan_results}")
    return scan_results

if __name__ == "__main__":
    ingest_and_scan_mainboard_ipos()
