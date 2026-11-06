import sqlite3
import os
import json
import time
from datetime import datetime
from typing import List, Dict, Any, Optional

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
DB_PATH = os.path.join(DATA_DIR, "zerobreakout.db")

def ensure_data_dir():
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR, exist_ok=True)

def get_connection() -> sqlite3.Connection:
    ensure_data_dir()
    conn = sqlite3.connect(DB_PATH, timeout=60.0)
    conn.row_factory = sqlite3.Row
    # Enable WAL mode with 30s busy timeout and NORMAL sync for non-blocking concurrency
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=30000;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn

def init_db():
    ensure_data_dir()
    conn = get_connection()
    cursor = conn.cursor()

    # 1. Stocks metadata table with All-Time High tracking
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS stocks (
        symbol TEXT PRIMARY KEY,
        company_name TEXT NOT NULL,
        sector TEXT DEFAULT 'General',
        market_cap_cr REAL DEFAULT 0,
        all_time_high REAL DEFAULT 0,
        ath_date TEXT,
        listing_date TEXT,
        is_active INTEGER DEFAULT 1,
        updated_at TEXT
    );
    """)

    # 2. Daily Price History table (5+ years daily OHLCV)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS price_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT NOT NULL,
        date TEXT NOT NULL,
        open REAL NOT NULL,
        high REAL NOT NULL,
        low REAL NOT NULL,
        close REAL NOT NULL,
        volume INTEGER NOT NULL,
        UNIQUE(symbol, date),
        FOREIGN KEY (symbol) REFERENCES stocks(symbol) ON DELETE CASCADE
    );
    """)

    # Indexes for fast historical query lookups
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_price_symbol_date ON price_history (symbol, date DESC);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_price_date ON price_history (date DESC);")

    # 3. Precomputed Pattern Signals table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS signals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT NOT NULL,
        pattern_type TEXT NOT NULL,
        trigger_date TEXT NOT NULL,
        pivot_price REAL NOT NULL,
        current_price REAL NOT NULL,
        percent_vs_pivot REAL NOT NULL,
        metadata_json TEXT DEFAULT '{}',
        created_at TEXT NOT NULL,
        UNIQUE(symbol, pattern_type, trigger_date),
        FOREIGN KEY (symbol) REFERENCES stocks(symbol) ON DELETE CASCADE
    );
    """)

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_signals_trigger_date ON signals (trigger_date DESC);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_signals_pattern ON signals (pattern_type);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_signals_symbol ON signals (symbol);")

    # 4. Watchlist table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS watchlist (
        user_id TEXT DEFAULT 'default_user',
        symbol TEXT NOT NULL,
        created_at TEXT NOT NULL,
        PRIMARY KEY(user_id, symbol),
        FOREIGN KEY (symbol) REFERENCES stocks(symbol) ON DELETE CASCADE
    );
    """)

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_watchlist_user ON watchlist (user_id);")

    # 5. Push Notification Subscriptions table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS push_subscriptions (
        endpoint TEXT PRIMARY KEY,
        p256dh TEXT NOT NULL,
        auth TEXT NOT NULL,
        user_id TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    """)

    conn.commit()
    conn.close()

def upsert_stock(symbol: str, company_name: str, sector: str = "General", market_cap_cr: float = 0, all_time_high: float = 0, ath_date: str = None, listing_date: str = None):
    conn = get_connection()
    now_str = datetime.now().isoformat()
    with conn:
        conn.execute("""
        INSERT INTO stocks (symbol, company_name, sector, market_cap_cr, all_time_high, ath_date, listing_date, is_active, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)
        ON CONFLICT(symbol) DO UPDATE SET
            company_name=CASE WHEN excluded.company_name != excluded.symbol AND excluded.company_name != '' THEN excluded.company_name ELSE stocks.company_name END,
            sector=CASE WHEN excluded.sector != 'General' AND excluded.sector != '' THEN excluded.sector ELSE stocks.sector END,
            market_cap_cr=CASE WHEN excluded.market_cap_cr > 0 THEN excluded.market_cap_cr ELSE stocks.market_cap_cr END,
            all_time_high=CASE WHEN excluded.all_time_high > stocks.all_time_high THEN excluded.all_time_high ELSE stocks.all_time_high END,
            ath_date=CASE WHEN excluded.all_time_high > stocks.all_time_high THEN excluded.ath_date ELSE stocks.ath_date END,
            listing_date=CASE WHEN excluded.listing_date IS NOT NULL THEN excluded.listing_date ELSE stocks.listing_date END,
            updated_at=excluded.updated_at;
        """, (symbol, company_name, sector, market_cap_cr, all_time_high, ath_date, listing_date, now_str))
    conn.close()

def upsert_price_batch(prices: List[tuple]):
    """prices is a list of (symbol, date, open, high, low, close, volume)"""
    if not prices:
        return
    conn = get_connection()
    with conn:
        conn.executemany("""
        INSERT INTO price_history (symbol, date, open, high, low, close, volume)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(symbol, date) DO UPDATE SET
            open=excluded.open,
            high=excluded.high,
            low=excluded.low,
            close=excluded.close,
            volume=excluded.volume;
        """, prices)
    conn.close()

def update_stock_ath_from_history(symbol: str):
    """Calculates and updates ATH from the highest recorded high in price_history (or external ATH)"""
    conn = get_connection()
    with conn:
        row = conn.execute("""
        SELECT MAX(high) as max_high, date FROM price_history 
        WHERE symbol = ? GROUP BY symbol;
        """, (symbol,)).fetchone()
        if row and row["max_high"]:
            conn.execute("""
            UPDATE stocks 
            SET all_time_high = CASE WHEN ? > all_time_high THEN ? ELSE all_time_high END,
                ath_date = CASE WHEN ? > all_time_high THEN ? ELSE ath_date END
            WHERE symbol = ?;
            """, (row["max_high"], row["max_high"], row["max_high"], row["date"], symbol))
    conn.close()

def insert_signals_batch(signals: List[Dict[str, Any]]):
    """signals list of dicts: symbol, pattern_type, trigger_date, pivot_price, current_price, percent_vs_pivot, metadata"""
    if not signals:
        return
    conn = get_connection()
    now_str = datetime.now().isoformat()
    with conn:
        rows = [
            (
                s["symbol"],
                s["pattern_type"],
                s["trigger_date"],
                s["pivot_price"],
                s["current_price"],
                s["percent_vs_pivot"],
                json.dumps(s.get("metadata", {})),
                now_str
            )
            for s in signals
        ]
        conn.executemany("""
        INSERT INTO signals (symbol, pattern_type, trigger_date, pivot_price, current_price, percent_vs_pivot, metadata_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(symbol, pattern_type, trigger_date) DO UPDATE SET
            pivot_price=excluded.pivot_price,
            current_price=excluded.current_price,
            percent_vs_pivot=excluded.percent_vs_pivot,
            metadata_json=excluded.metadata_json,
            created_at=excluded.created_at;
        """, rows)
    conn.close()

_latest_prices_cache = {
    "timestamp": 0.0,
    "current_prices": {},
    "prev_prices": {}
}

def get_recent_price_maps(conn, max_age_seconds: float = 60.0):
    """
    High-performance in-memory batch price map.
    Eliminates 150+ N+1 queries by fetching latest and previous day prices in 2 fast index scans.
    """
    global _latest_prices_cache
    now = time.time()
    if (now - _latest_prices_cache["timestamp"] < max_age_seconds) and _latest_prices_cache["current_prices"]:
        return _latest_prices_cache["current_prices"], _latest_prices_cache["prev_prices"]

    try:
        dates_rows = conn.execute("SELECT DISTINCT date FROM price_history ORDER BY date DESC LIMIT 2").fetchall()
        if not dates_rows:
            return {}, {}
        
        d_now = dates_rows[0]["date"]
        d_prev = dates_rows[1]["date"] if len(dates_rows) > 1 else None

        cur_rows = conn.execute("SELECT symbol, close FROM price_history WHERE date = ?", (d_now,)).fetchall()
        cur_map = {r["symbol"]: r["close"] for r in cur_rows}

        prev_map = {}
        if d_prev:
            prev_rows = conn.execute("SELECT symbol, close FROM price_history WHERE date = ?", (d_prev,)).fetchall()
            prev_map = {r["symbol"]: r["close"] for r in prev_rows}

        _latest_prices_cache["timestamp"] = now
        _latest_prices_cache["current_prices"] = cur_map
        _latest_prices_cache["prev_prices"] = prev_map
        return cur_map, prev_map
    except Exception as e:
        return {}, {}

def get_latest_signals(pattern_type: Optional[str] = None, search_query: Optional[str] = None, limit: int = 150, min_mcap_cr: float = 2000.0) -> List[Dict[str, Any]]:
    """Fetches signals with stock metadata for the Scanner view (minimum ₹2,000 Cr Market Cap)"""
    conn = get_connection()
    query = """
    SELECT 
        s.id,
        s.symbol,
        s.pattern_type,
        s.trigger_date,
        s.pivot_price,
        s.current_price,
        s.percent_vs_pivot,
        s.metadata_json,
        st.company_name,
        st.sector,
        st.market_cap_cr,
        st.all_time_high
    FROM signals s
    JOIN stocks st ON s.symbol = st.symbol
    WHERE st.is_active = 1 AND st.market_cap_cr >= ?
    """
    params = [min_mcap_cr]
    
    # Handle Fresh Breakout / Today's Breakout filter
    is_fresh_filter = bool(pattern_type and pattern_type.lower().replace("⚡", "").strip() in [
        "fresh", "fresh breakout", "today", "today breakout", "today's breakout", "fresh today", "fresh today breakout"
    ])

    if is_fresh_filter:
        query += """ AND s.trigger_date = (SELECT MAX(date) FROM price_history)
                     AND (
                         s.metadata_json LIKE '%"is_fresh": true%' 
                         OR s.metadata_json LIKE '%"is_fresh":true%'
                         OR s.percent_vs_pivot >= -1.0
                     )"""
    elif pattern_type and pattern_type.lower() != "all":
        query += " AND LOWER(s.pattern_type) = LOWER(?)"
        params.append(pattern_type)

    if search_query:
        query += " AND (s.symbol LIKE ? OR st.company_name LIKE ?)"
        wildcard = f"%{search_query.strip().upper()}%"
        params.extend([wildcard, f"%{search_query.strip()}%"])

    if is_fresh_filter:
        query += " ORDER BY s.percent_vs_pivot DESC, s.trigger_date DESC LIMIT ?"
    else:
        query += " ORDER BY s.trigger_date DESC, s.id DESC LIMIT ?"
    params.append(limit)

    cursor = conn.execute(query, params)
    rows = cursor.fetchall()

    cur_map, prev_map = get_recent_price_maps(conn)

    result = []
    for r in rows:
        d = dict(r)
        if d.get("metadata_json"):
            try:
                d["metadata"] = json.loads(d["metadata_json"])
            except Exception:
                d["metadata"] = {}
        
        # Calculate instant day change from pre-fetched price map (0 extra queries)
        sym = d["symbol"]
        c_now = cur_map.get(sym, d.get("current_price", 0.0))
        c_prev = prev_map.get(sym, c_now)
        d["current_price"] = c_now
        d["change"] = round(c_now - c_prev, 2)
        d["change_pct"] = round(((c_now - c_prev) / c_prev) * 100, 2) if c_prev else 0.0

        result.append(d)
    conn.close()
    return result

def get_stock_setup(symbol: str) -> Optional[Dict[str, Any]]:
    """Fetches full stock setup info for the Setup tab"""
    conn = get_connection()
    stock_row = conn.execute("SELECT * FROM stocks WHERE symbol = ?", (symbol.upper(),)).fetchone()
    if not stock_row:
        conn.close()
        return None
    stock_dict = dict(stock_row)

    # Get latest signal for this stock
    signal_row = conn.execute("""
    SELECT * FROM signals 
    WHERE symbol = ? 
    ORDER BY trigger_date DESC, id DESC LIMIT 1
    """, (symbol.upper(),)).fetchone()
    if signal_row:
        sig_dict = dict(signal_row)
        if sig_dict.get("metadata_json"):
            try:
                sig_dict["metadata"] = json.loads(sig_dict["metadata_json"])
            except Exception:
                sig_dict["metadata"] = {}
        stock_dict["latest_signal"] = sig_dict
    else:
        stock_dict["latest_signal"] = None

    # Get latest price & prev close for calculating day change
    prices = conn.execute("""
    SELECT date, open, high, low, close, volume FROM price_history
    WHERE symbol = ?
    ORDER BY date DESC LIMIT 2
    """, (symbol.upper(),)).fetchall()

    if prices:
        current_candle = dict(prices[0])
        stock_dict["current_price"] = current_candle["close"]
        stock_dict["latest_date"] = current_candle["date"]
        if len(prices) > 1:
            prev_close = dict(prices[1])["close"]
            change = current_candle["close"] - prev_close
            change_pct = (change / prev_close) * 100 if prev_close else 0.0
            stock_dict["prev_close"] = prev_close
            stock_dict["change"] = round(change, 2)
            stock_dict["change_pct"] = round(change_pct, 2)
        else:
            stock_dict["prev_close"] = current_candle["open"]
            change = current_candle["close"] - current_candle["open"]
            change_pct = (change / current_candle["open"]) * 100 if current_candle["open"] else 0.0
            stock_dict["change"] = round(change, 2)
            stock_dict["change_pct"] = round(change_pct, 2)
    else:
        stock_dict["current_price"] = stock_dict.get("all_time_high", 0)
        stock_dict["change"] = 0.0
        stock_dict["change_pct"] = 0.0

    conn.close()
    return stock_dict

def get_stock_price_history(symbol: str, limit_days: int = 1250) -> List[Dict[str, Any]]:
    """Fetches chronological daily candles for charting"""
    conn = get_connection()
    rows = conn.execute("""
    SELECT date, open, high, low, close, volume
    FROM price_history
    WHERE symbol = ?
    ORDER BY date ASC
    """, (symbol.upper(),)).fetchall()
    conn.close()

    if limit_days and len(rows) > limit_days:
        rows = rows[-limit_days:]

    return [dict(r) for r in rows]

def get_watchlist(user_id: str = "default_user") -> List[Dict[str, Any]]:
    conn = get_connection()
    rows = conn.execute("""
    SELECT 
        w.symbol,
        w.created_at,
        st.company_name,
        st.sector,
        st.market_cap_cr
    FROM watchlist w
    JOIN stocks st ON w.symbol = st.symbol
    WHERE w.user_id = ?
    ORDER BY w.created_at DESC
    """, (user_id,)).fetchall()

    results = []
    for r in rows:
        d = dict(r)
        setup = get_stock_setup(d["symbol"])
        if setup:
            d["current_price"] = setup.get("current_price", 0)
            d["change"] = setup.get("change", 0)
            d["change_pct"] = setup.get("change_pct", 0)
            d["latest_signal"] = setup.get("latest_signal")
        results.append(d)

    conn.close()
    return results

def is_in_watchlist(symbol: str, user_id: str = "default_user") -> bool:
    conn = get_connection()
    row = conn.execute("SELECT 1 FROM watchlist WHERE user_id = ? AND symbol = ?", (user_id, symbol.upper())).fetchone()
    conn.close()
    return bool(row)

def toggle_watchlist(symbol: str, user_id: str = "default_user") -> bool:
    """Returns True if added, False if removed"""
    conn = get_connection()
    symbol = symbol.upper()
    existing = conn.execute("SELECT 1 FROM watchlist WHERE user_id = ? AND symbol = ?", (user_id, symbol)).fetchone()
    if existing:
        with conn:
            conn.execute("DELETE FROM watchlist WHERE user_id = ? AND symbol = ?", (user_id, symbol))
        conn.close()
        return False
    else:
        now_str = datetime.now().isoformat()
        with conn:
            conn.execute("INSERT OR REPLACE INTO watchlist (user_id, symbol, created_at) VALUES (?, ?, ?)", (user_id, symbol, now_str))
        conn.close()
        return True

def get_all_active_symbols(min_mcap_cr: float = 2000.0) -> List[Dict[str, Any]]:
    conn = get_connection()
    rows = conn.execute("SELECT symbol, company_name, sector, market_cap_cr, all_time_high, ath_date, listing_date FROM stocks WHERE is_active = 1 AND market_cap_cr >= ?", (min_mcap_cr,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def save_push_subscription(endpoint: str, p256dh: str, auth: str, user_id: Optional[str] = None) -> bool:
    """Saves or updates a Web Push subscription in the database."""
    conn = get_connection()
    now_str = datetime.now().isoformat()
    try:
        with conn:
            conn.execute("""
            INSERT INTO push_subscriptions (endpoint, p256dh, auth, user_id, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(endpoint) DO UPDATE SET
                p256dh=excluded.p256dh,
                auth=excluded.auth,
                user_id=COALESCE(excluded.user_id, push_subscriptions.user_id),
                updated_at=excluded.updated_at;
            """, (endpoint, p256dh, auth, user_id, now_str))
        return True
    finally:
        conn.close()

def get_all_push_subscriptions() -> List[Dict[str, Any]]:
    """Retrieves all active push subscriptions."""
    conn = get_connection()
    try:
        rows = conn.execute("SELECT endpoint, p256dh, auth, user_id, created_at FROM push_subscriptions").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()

def delete_push_subscription(endpoint: str) -> bool:
    """Deletes an invalid or expired push subscription."""
    conn = get_connection()
    try:
        with conn:
            conn.execute("DELETE FROM push_subscriptions WHERE endpoint = ?", (endpoint,))
        return True
    finally:
        conn.close()

def is_push_subscribed(endpoint: str) -> bool:
    conn = get_connection()
    try:
        row = conn.execute("SELECT 1 FROM push_subscriptions WHERE endpoint = ?", (endpoint,)).fetchone()
        return bool(row)
    finally:
        conn.close()

