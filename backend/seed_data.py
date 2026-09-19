import os
import sys
import logging
import time
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

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("ZeroBreakout.RealDataIngest")

# Comprehensive Universe of Top Liquid NSE Stocks with proper NSE ticker symbols
REAL_NSE_UNIVERSE = [
    # Large Cap Benchmarks
    {"symbol": "RELIANCE", "ticker": "RELIANCE.NS", "name": "Reliance Industries Ltd", "sector": "Energy / Conglomerate", "mcap": 2015000},
    {"symbol": "TCS", "ticker": "TCS.NS", "name": "Tata Consultancy Services", "sector": "IT & Software", "mcap": 1490000},
    {"symbol": "HDFCBANK", "ticker": "HDFCBANK.NS", "name": "HDFC Bank Ltd", "sector": "Banking & Finance", "mcap": 1280000},
    {"symbol": "INFY", "ticker": "INFY.NS", "name": "Infosys Ltd", "sector": "IT & Software", "mcap": 780000},
    {"symbol": "BHARTIARTL", "ticker": "BHARTIARTL.NS", "name": "Bharti Airtel Ltd", "sector": "Telecom", "mcap": 910000},
    {"symbol": "ICICIBANK", "ticker": "ICICIBANK.NS", "name": "ICICI Bank Ltd", "sector": "Banking & Finance", "mcap": 870000},
    {"symbol": "SBIN", "ticker": "SBIN.NS", "name": "State Bank of India", "sector": "Banking & Finance", "mcap": 725000},
    {"symbol": "ITC", "ticker": "ITC.NS", "name": "ITC Ltd", "sector": "FMCG", "mcap": 620000},
    {"symbol": "LT", "ticker": "LT.NS", "name": "Larsen & Toubro Ltd", "sector": "Capital Goods / EPC", "mcap": 498000},
    
    # High-Momentum Breakout & Growth Stars
    {"symbol": "TRENT", "ticker": "TRENT.NS", "name": "Trent Ltd (Westside/Zudio)", "sector": "Retail / Consumer", "mcap": 258000},
    {"symbol": "BEL", "ticker": "BEL.NS", "name": "Bharat Electronics Ltd", "sector": "Defence / Aerospace", "mcap": 218000},
    {"symbol": "HAL", "ticker": "HAL.NS", "name": "Hindustan Aeronautics Ltd", "sector": "Defence / Aerospace", "mcap": 312000},
    {"symbol": "DIXON", "ticker": "DIXON.NS", "name": "Dixon Technologies Ltd", "sector": "Electronics Manufacturing", "mcap": 78000},
    {"symbol": "PERSISTENT", "ticker": "PERSISTENT.NS", "name": "Persistent Systems Ltd", "sector": "IT & Software", "mcap": 82000},
    {"symbol": "POLYCAB", "ticker": "POLYCAB.NS", "name": "Polycab India Ltd", "sector": "Cables & Wires", "mcap": 105000},
    {"symbol": "VBL", "ticker": "VBL.NS", "name": "Varun Beverages Ltd", "sector": "FMCG / Beverages", "mcap": 196000},
    {"symbol": "SUZLON", "ticker": "SUZLON.NS", "name": "Suzlon Energy Ltd", "sector": "Renewable Energy", "mcap": 98000},
    {"symbol": "BSE", "ticker": "BSE.NS", "name": "BSE Ltd", "sector": "Financial Capital Markets", "mcap": 41000},
    {"symbol": "KAYNES", "ticker": "KAYNES.NS", "name": "Kaynes Technology India", "sector": "EMS / Electronics", "mcap": 32000},
    {"symbol": "TITAN", "ticker": "TITAN.NS", "name": "Titan Company Ltd", "sector": "Consumer / Jewellery", "mcap": 318000},
    {"symbol": "BAJFINANCE", "ticker": "BAJFINANCE.NS", "name": "Bajaj Finance Ltd", "sector": "NBFC / Lending", "mcap": 450000},
    {"symbol": "ASIANPAINT", "ticker": "ASIANPAINT.NS", "name": "Asian Paints Ltd", "sector": "Paints & Chemicals", "mcap": 275000},
    {"symbol": "COALINDIA", "ticker": "COALINDIA.NS", "name": "Coal India Ltd", "sector": "Mining & Metals", "mcap": 310000},
    
    # Defence, PSU & Capital Goods
    {"symbol": "MAZDOCK", "ticker": "MAZDOCK.NS", "name": "Mazagon Dock Shipbuilders", "sector": "Defence / Shipbuilding", "mcap": 85000},
    {"symbol": "COCHINSHIP", "ticker": "COCHINSHIP.NS", "name": "Cochin Shipyard Ltd", "sector": "Defence / Shipbuilding", "mcap": 48000},
    {"symbol": "RVNL", "ticker": "RVNL.NS", "name": "Rail Vikas Nigam Ltd", "sector": "Railways Infrastructure", "mcap": 92000},
    {"symbol": "IRFC", "ticker": "IRFC.NS", "name": "Indian Railway Finance Corp", "sector": "Railway Finance", "mcap": 210000},
    {"symbol": "IREDA", "ticker": "IREDA.NS", "name": "Indian Renewable Energy Dev", "sector": "Green Energy Finance", "mcap": 62000},
    {"symbol": "BHEL", "ticker": "BHEL.NS", "name": "Bharat Heavy Electricals Ltd", "sector": "Power Equipment", "mcap": 95000},
    
    # Power & Infrastructure
    {"symbol": "TATAPOWER", "ticker": "TATAPOWER.NS", "name": "Tata Power Company Ltd", "sector": "Power & Utilities", "mcap": 138000},
    {"symbol": "NTPC", "ticker": "NTPC.NS", "name": "NTPC Ltd", "sector": "Power Generation", "mcap": 380000},
    {"symbol": "POWERGRID", "ticker": "POWERGRID.NS", "name": "Power Grid Corp of India", "sector": "Power Transmission", "mcap": 310000},
    {"symbol": "ADANIENT", "ticker": "ADANIENT.NS", "name": "Adani Enterprises Ltd", "sector": "Conglomerate", "mcap": 340000},
    {"symbol": "ADANIPORTS", "ticker": "ADANIPORTS.NS", "name": "Adani Ports & SEZ", "sector": "Ports & Logistics", "mcap": 315000},
    
    # IT, Auto, Pharma & Consumer
    {"symbol": "COFORGE", "ticker": "COFORGE.NS", "name": "Coforge Ltd", "sector": "IT & Software", "mcap": 42000},
    {"symbol": "KPITTECH", "ticker": "KPITTECH.NS", "name": "KPIT Technologies Ltd", "sector": "Automotive Software", "mcap": 46000},
    {"symbol": "TATAELXSI", "ticker": "TATAELXSI.NS", "name": "Tata Elxsi Ltd", "sector": "Design & Tech", "mcap": 44000},
    {"symbol": "MARUTI", "ticker": "MARUTI.NS", "name": "Maruti Suzuki India Ltd", "sector": "Automobile", "mcap": 390000},
    {"symbol": "M&M", "ticker": "M&M.NS", "name": "Mahindra & Mahindra Ltd", "sector": "Automobile", "mcap": 345000},
    {"symbol": "HEROMOTOCO", "ticker": "HEROMOTOCO.NS", "name": "Hero MotoCorp Ltd", "sector": "Automobile", "mcap": 105000},
    {"symbol": "EICHERMOT", "ticker": "EICHERMOT.NS", "name": "Eicher Motors Ltd", "sector": "Automobile", "mcap": 132000},
    {"symbol": "DMART", "ticker": "DMART.NS", "name": "Avenue Supermarts (DMart)", "sector": "Retail Supermarkets", "mcap": 310000},
    {"symbol": "JUBLFOOD", "ticker": "JUBLFOOD.NS", "name": "Jubilant FoodWorks Ltd", "sector": "QSR / Food Services", "mcap": 41000},
    {"symbol": "SUNPHARMA", "ticker": "SUNPHARMA.NS", "name": "Sun Pharmaceutical Ind", "sector": "Pharmaceuticals", "mcap": 420000},
    {"symbol": "CIPLA", "ticker": "CIPLA.NS", "name": "Cipla Ltd", "sector": "Pharmaceuticals", "mcap": 128000},
    {"symbol": "DRREDDY", "ticker": "DRREDDY.NS", "name": "Dr Reddy's Laboratories", "sector": "Pharmaceuticals", "mcap": 110000},
    {"symbol": "MAXHEALTH", "ticker": "MAXHEALTH.NS", "name": "Max Healthcare Institute", "sector": "Healthcare Services", "mcap": 88000}
]

def clear_all_mock_data():
    """Wipes all mock data completely from database tables"""
    logger.info("Purging all old mock data from database...")
    conn = get_connection()
    with conn:
        conn.execute("DELETE FROM signals;")
        conn.execute("DELETE FROM price_history;")
        conn.execute("DELETE FROM stocks;")
        conn.execute("DELETE FROM watchlist;")
    conn.close()
    logger.info("Database cleanly wiped.")

def fetch_and_populate_real_data():
    """
    Downloads 100% REAL 5-year daily OHLCV from NSE for all universe stocks,
    populates price_history, records lifetime ATH, and triggers pattern scanner.
    """
    import yfinance as yf

    clear_all_mock_data()
    init_db()

    tickers_list = [item["ticker"] for item in REAL_NSE_UNIVERSE]
    ticker_to_meta = {item["ticker"]: item for item in REAL_NSE_UNIVERSE}

    logger.info(f"Downloading REAL 5-year OHLCV for {len(tickers_list)} NSE stocks via multi-threaded bulk download...")
    
    try:
        data = yf.download(tickers_list, period="5y", group_by="ticker", threads=True, progress=False)
    except Exception as e:
        logger.error(f"Error during bulk download: {e}")
        data = None

    if data is None or data.empty:
        logger.error("Failed to download real market data.")
        return

    success_stocks = 0
    total_records = 0

    for ticker in tickers_list:
        meta = ticker_to_meta[ticker]
        sym = meta["symbol"]
        
        try:
            # Handle multi-index column access
            if ticker in data.columns.levels[0]:
                df_ticker = data[ticker].dropna(subset=["Close"]).copy()
            else:
                continue

            if df_ticker.empty or len(df_ticker) < 10:
                continue

            # Extract real daily OHLCV
            price_rows = []
            for dt, row in df_ticker.iterrows():
                date_str = dt.strftime("%Y-%m-%d")
                o = round(float(row["Open"]), 2)
                h = round(float(row["High"]), 2)
                l = round(float(row["Low"]), 2)
                c = round(float(row["Close"]), 2)
                v = int(row.get("Volume", 0) or 0)
                price_rows.append((sym, date_str, o, h, l, c, v))

            if not price_rows:
                continue

            # Calculate genuine historical All-Time High
            all_highs = [p[3] for p in price_rows]
            real_ath = float(max(all_highs))
            ath_idx = all_highs.index(real_ath)
            ath_date = price_rows[ath_idx][1]

            # Upsert real stock metadata
            upsert_stock(
                symbol=sym,
                company_name=meta["name"],
                sector=meta["sector"],
                market_cap_cr=meta["mcap"],
                all_time_high=real_ath,
                ath_date=ath_date
            )

            # Batch insert real price history
            upsert_price_batch(price_rows)
            success_stocks += 1
            total_records += len(price_rows)
            logger.info(f"Synced {len(price_rows)} REAL daily candles for {sym} (Real ATH: Rs {real_ath:.2f} on {ath_date})")

        except Exception as err:
            logger.warning(f"Error processing real data for {sym}: {err}")

    logger.info(f"Successfully populated {success_stocks} REAL stocks with {total_records} real historical candles.")
    
    # Run Pattern Engine over 100% genuine market data
    logger.info("Executing technical pattern detection engine across REAL market data...")
    scan_results = pattern_engine.scan_all_stocks()
    logger.info(f"Real Pattern Scan Complete: {scan_results}")
    return scan_results

def seed_database_if_empty():
    """Ensures database is initialized with full institutional stocks, breakout signals, and multi-year price history"""
    from .database import init_db, get_all_active_symbols, get_connection, DB_PATH
    import gzip, shutil

    init_db()
    
    conn = get_connection()
    price_count = 0
    stock_count = 0
    try:
        price_count = conn.execute("SELECT COUNT(*) FROM price_history").fetchone()[0]
        stock_count = conn.execute("SELECT COUNT(*) FROM stocks WHERE is_active = 1").fetchone()[0]
    except Exception:
        pass
    conn.close()

    if price_count < 1000 or stock_count < 500:
        logger.info(f"Database currently holds {stock_count} stocks and {price_count} price history candles. Restoring pre-packaged multi-year history bundle...")
        
        gz_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "seed_data", "seed_history.db.gz")
        uncompressed_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "seed_data", "seed_history.db")

        # 1. Primary: Unpack compressed binary database bundle with full multi-year OHLCV
        if os.path.exists(gz_path):
            try:
                with gzip.open(gz_path, "rb") as f_in, open(DB_PATH, "wb") as f_out:
                    shutil.copyfileobj(f_in, f_out)
                logger.info("Successfully restored complete multi-year price history and universe database from seed_history.db.gz!")
                return
            except Exception as e:
                logger.error(f"Error decompressing seed_history.db.gz: {e}")

        # 2. Secondary fallback: Uncompressed seed database
        if os.path.exists(uncompressed_path):
            try:
                shutil.copy2(uncompressed_path, DB_PATH)
                logger.info("Successfully copied seed_history.db into active database!")
                return
            except Exception as e:
                logger.error(f"Error copying seed_history.db: {e}")

        # 3. Tertiary fallback: JSON universe seed
        seed_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "seed_data", "universe_seed.json")
        if os.path.exists(seed_path):
            try:
                import json
                with open(seed_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                stocks = data.get("stocks", [])
                signals = data.get("signals", [])
                
                conn = get_connection()
                with conn:
                    for s in stocks:
                        conn.execute("""
                            INSERT OR REPLACE INTO stocks (symbol, company_name, sector, market_cap_cr, all_time_high, ath_date, listing_date, is_active, updated_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            s.get("symbol"), s.get("company_name"), s.get("sector"), s.get("market_cap_cr", 2000.0),
                            s.get("all_time_high", 0.0), s.get("ath_date"), s.get("listing_date"),
                            s.get("is_active", 1), s.get("updated_at")
                        ))
                    for sig in signals:
                        conn.execute("""
                            INSERT OR REPLACE INTO signals (symbol, pattern_type, trigger_date, pivot_price, current_price, percent_vs_pivot, metadata_json, created_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            sig.get("symbol"), sig.get("pattern_type"), sig.get("trigger_date"),
                            sig.get("pivot_price", 0.0), sig.get("current_price", 0.0),
                            sig.get("percent_vs_pivot", 0.0), sig.get("metadata_json", "{}"),
                            sig.get("created_at")
                        ))
                conn.close()
                logger.info(f"Successfully seeded {len(stocks)} institutional stocks and {len(signals)} breakout signals from JSON bundle!")
                return
            except Exception as e:
                logger.error(f"Error seeding from universe_seed.json: {e}")
        
        # Fallback to online fetch if seed file not present
        fetch_and_populate_real_data()
    else:
        logger.info(f"Database currently holds {stock_count} active real stocks and {price_count} price history candles.")

if __name__ == "__main__":
    fetch_and_populate_real_data()
