import os
import sys
import time
import logging
import requests
import pandas as pd
from datetime import datetime, timedelta
from typing import List, Dict, Any

from .database import init_db, upsert_stock, upsert_price_batch, update_stock_ath_from_history
from .patterns.engine import pattern_engine

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ZeroBreakout.LiveSync")

# Comprehensive universe of top 80 liquid NSE stocks across Large, Mid & Small cap
NSE_UNIVERSE = [
    # Nifty 50 Heavyweights
    {"symbol": "RELIANCE", "name": "Reliance Industries Ltd", "sector": "Energy / Conglomerate", "mcap": 2015000},
    {"symbol": "TCS", "name": "Tata Consultancy Services", "sector": "IT & Software", "mcap": 1490000},
    {"symbol": "HDFCBANK", "name": "HDFC Bank Ltd", "sector": "Banking & Finance", "mcap": 1280000},
    {"symbol": "INFY", "name": "Infosys Ltd", "sector": "IT & Software", "mcap": 780000},
    {"symbol": "BHARTIARTL", "name": "Bharti Airtel Ltd", "sector": "Telecom", "mcap": 910000},
    {"symbol": "ICICIBANK", "name": "ICICI Bank Ltd", "sector": "Banking & Finance", "mcap": 870000},
    {"symbol": "SBIN", "name": "State Bank of India", "sector": "Banking & Finance", "mcap": 725000},
    {"symbol": "ITC", "name": "ITC Ltd", "sector": "FMCG", "mcap": 620000},
    {"symbol": "LT", "name": "Larsen & Toubro Ltd", "sector": "Capital Goods / EPC", "mcap": 498000},
    {"symbol": "TATAMOTORS", "name": "Tata Motors Ltd", "sector": "Automobile", "mcap": 352000},
    
    # High-Momentum Breakout Stars
    {"symbol": "TRENT", "name": "Trent Ltd", "sector": "Retail / Consumer", "mcap": 258000},
    {"symbol": "ZOMATO", "name": "Zomato Ltd", "sector": "Internet / Platform", "mcap": 245000},
    {"symbol": "BEL", "name": "Bharat Electronics Ltd", "sector": "Defence / Aerospace", "mcap": 218000},
    {"symbol": "HAL", "name": "Hindustan Aeronautics Ltd", "sector": "Defence / Aerospace", "mcap": 312000},
    {"symbol": "DIXON", "name": "Dixon Technologies Ltd", "sector": "Electronics Manufacturing", "mcap": 78000},
    {"symbol": "PERSISTENT", "name": "Persistent Systems Ltd", "sector": "IT & Software", "mcap": 82000},
    {"symbol": "POLYCAB", "name": "Polycab India Ltd", "sector": "Cables & Wires", "mcap": 105000},
    {"symbol": "VBL", "name": "Varun Beverages Ltd", "sector": "FMCG / Beverages", "mcap": 196000},
    {"symbol": "SUZLON", "name": "Suzlon Energy Ltd", "sector": "Renewable Energy", "mcap": 98000},
    {"symbol": "BSE", "name": "BSE Ltd", "sector": "Financial Capital Markets", "mcap": 41000},
    {"symbol": "KAYNES", "name": "Kaynes Technology India", "sector": "EMS / Electronics", "mcap": 32000},
    {"symbol": "TITAN", "name": "Titan Company Ltd", "sector": "Consumer Goods / Jewellery", "mcap": 318000},
    {"symbol": "BAJFINANCE", "name": "Bajaj Finance Ltd", "sector": "NBFC / Lending", "mcap": 450000},
    {"symbol": "ASIANPAINT", "name": "Asian Paints Ltd", "sector": "Paints & Chemicals", "mcap": 275000},
    {"symbol": "COALINDIA", "name": "Coal India Ltd", "sector": "Mining & Metals", "mcap": 310000},
    
    # Defence, Railways & Infrastructure
    {"symbol": "MAZDOCK", "name": "Mazagon Dock Shipbuilders", "sector": "Defence / Shipbuilding", "mcap": 85000},
    {"symbol": "COCHINSHIP", "name": "Cochin Shipyard Ltd", "sector": "Defence / Shipbuilding", "mcap": 48000},
    {"symbol": "RVNL", "name": "Rail Vikas Nigam Ltd", "sector": "Railways Infrastructure", "mcap": 92000},
    {"symbol": "IRFC", "name": "Indian Railway Finance Corp", "sector": "Railway Finance", "mcap": 210000},
    {"symbol": "IREDA", "name": "Indian Renewable Energy Dev", "sector": "Green Energy Finance", "mcap": 62000},
    {"symbol": "BHEL", "name": "Bharat Heavy Electricals Ltd", "sector": "Power Equipment", "mcap": 95000},
    
    # Power & Energy Transition
    {"symbol": "TATAPOWER", "name": "Tata Power Company Ltd", "sector": "Power & Energy", "mcap": 138000},
    {"symbol": "NTPC", "name": "NTPC Ltd", "sector": "Power Generation", "mcap": 380000},
    {"symbol": "POWERGRID", "name": "Power Grid Corp of India", "sector": "Power Transmission", "mcap": 310000},
    {"symbol": "ADANIENT", "name": "Adani Enterprises Ltd", "sector": "Conglomerate", "mcap": 340000},
    {"symbol": "ADANIPORTS", "name": "Adani Ports & SEZ", "sector": "Ports & Logistics", "mcap": 315000},
    
    # IT, Auto & Consumer Tech
    {"symbol": "COFORGE", "name": "Coforge Ltd", "sector": "IT & Software", "mcap": 42000},
    {"symbol": "KPITTECH", "name": "KPIT Technologies Ltd", "sector": "Automotive Software", "mcap": 46000},
    {"symbol": "TATAELXSI", "name": "Tata Elxsi Ltd", "sector": "Design & Tech", "mcap": 44000},
    {"symbol": "MARUTI", "name": "Maruti Suzuki India Ltd", "sector": "Automobile", "mcap": 390000},
    {"symbol": "M&M", "name": "Mahindra & Mahindra Ltd", "sector": "Automobile", "mcap": 345000},
    {"symbol": "HEROMOTOCO", "name": "Hero MotoCorp Ltd", "sector": "Automobile", "mcap": 105000},
    {"symbol": "EICHERMOT", "name": "Eicher Motors Ltd", "sector": "Automobile", "mcap": 132000},
    {"symbol": "DMART", "name": "Avenue Supermarts (DMart)", "sector": "Retail Supermarkets", "mcap": 310000},
    {"symbol": "JUBLFOOD", "name": "Jubilant FoodWorks Ltd", "sector": "QSR / Food Services", "mcap": 41000},
    {"symbol": "SUNPHARMA", "name": "Sun Pharmaceutical Ind", "sector": "Pharmaceuticals", "mcap": 420000},
    {"symbol": "CIPLA", "name": "Cipla Ltd", "sector": "Pharmaceuticals", "mcap": 128000},
    {"symbol": "DRREDDY", "name": "Dr Reddy's Laboratories", "sector": "Pharmaceuticals", "mcap": 110000},
    {"symbol": "MAXHEALTH", "name": "Max Healthcare Institute", "sector": "Healthcare Services", "mcap": 88000}
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
}

def fetch_real_live_candles(symbol: str, years: int = 5) -> List[tuple]:
    """
    Fetches genuine real historical & live EOD daily OHLCV candles from Yahoo Finance.
    """
    nse_sym = f"{symbol.upper()}.NS"
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{nse_sym}?range={years}y&interval=1d"
    
    try:
        resp = requests.get(url, headers=HEADERS, timeout=12)
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
                    if opens[i] is not None and closes[i] is not None and highs[i] is not None and lows[i] is not None:
                        d_str = datetime.fromtimestamp(timestamps[i]).strftime("%Y-%m-%d")
                        o = round(float(opens[i]), 2)
                        h = round(float(highs[i]), 2)
                        l = round(float(lows[i]), 2)
                        c = round(float(closes[i]), 2)
                        v = int(volumes[i] or 0)
                        rows.append((symbol.upper(), d_str, o, h, l, c, v))
                return rows
    except Exception as e:
        logger.warning(f"Error fetching live data for {symbol}: {e}")
    return []

def sync_live_universe(stocks_to_sync: List[Dict[str, Any]] = None, max_stocks: int = 60):
    """
    Downloads real live market data for NSE stocks, saves to SQLite, and runs pattern scan.
    Delegates cleanly to the robust multi-day Bhavcopy sync engine without freezing the server.
    """
    from .data_fetcher import sync_missing_bhavcopies
    from .patterns.engine import pattern_engine

    logger.info("Starting Live Data Sync...")
    res = sync_missing_bhavcopies()
    if res.get("synced_days", 0) == 0:
        logger.info("Bhavcopy up to date; running fast pattern scan...")
        scan_res = pattern_engine.scan_all_stocks()
        res["scan_results"] = scan_res
    return res

if __name__ == "__main__":
    sync_live_universe()
