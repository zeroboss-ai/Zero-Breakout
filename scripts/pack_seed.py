import sqlite3
import gzip
import shutil
import os
import time

def pack_seed():
    start = time.time()
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src_db = os.path.join(root_dir, "data", "zerobreakout.db")
    seed_dir = os.path.join(root_dir, "backend", "seed_data")
    dst_db = os.path.join(seed_dir, "seed_history_clean.db")
    gz_path = os.path.join(seed_dir, "seed_history.db.gz")

    if os.path.exists(dst_db):
        os.remove(dst_db)

    conn_src = sqlite3.connect(src_db)
    conn_dst = sqlite3.connect(dst_db)
    conn_dst.execute("PRAGMA synchronous = OFF;")
    conn_dst.execute("PRAGMA journal_mode = MEMORY;")

    # 1. Stocks table
    conn_dst.execute("""
    CREATE TABLE stocks (
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
    stocks_rows = conn_src.execute("""
        SELECT symbol, company_name, sector, market_cap_cr, all_time_high, ath_date, listing_date, is_active, updated_at 
        FROM stocks 
        WHERE market_cap_cr >= 2000 OR symbol IN (SELECT symbol FROM signals)
    """).fetchall()
    with conn_dst:
        conn_dst.executemany("INSERT OR REPLACE INTO stocks VALUES (?,?,?,?,?,?,?,?,?)", stocks_rows)

    # 2. Signals table
    conn_dst.execute("""
    CREATE TABLE signals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT NOT NULL,
        pattern_type TEXT NOT NULL,
        trigger_date TEXT NOT NULL,
        pivot_price REAL NOT NULL,
        current_price REAL NOT NULL,
        percent_vs_pivot REAL NOT NULL,
        metadata_json TEXT DEFAULT '{}',
        created_at TEXT NOT NULL,
        UNIQUE(symbol, pattern_type, trigger_date)
    );
    """)
    signals_rows = conn_src.execute("SELECT id, symbol, pattern_type, trigger_date, pivot_price, current_price, percent_vs_pivot, metadata_json, created_at FROM signals").fetchall()
    with conn_dst:
        conn_dst.executemany("INSERT OR REPLACE INTO signals VALUES (?,?,?,?,?,?,?,?,?)", signals_rows)

    # 3. Price History table (Keep from 2024-08-01 to 2026-09-22 — ~290 trading days, >252 days for 52W High)
    conn_dst.execute("""
    CREATE TABLE price_history (
        symbol TEXT NOT NULL,
        date TEXT NOT NULL,
        open REAL NOT NULL,
        high REAL NOT NULL,
        low REAL NOT NULL,
        close REAL NOT NULL,
        volume INTEGER NOT NULL,
        PRIMARY KEY (symbol, date)
    );
    """)

    conn_dst.execute(f"ATTACH DATABASE '{src_db}' AS src;")
    with conn_dst:
        conn_dst.execute("""
            INSERT INTO price_history 
            SELECT ph.symbol, ph.date, ph.open, ph.high, ph.low, ph.close, ph.volume 
            FROM src.price_history ph
            WHERE ph.date >= '2024-08-01' 
            AND ph.symbol IN (SELECT symbol FROM stocks);
        """)
    conn_dst.execute("DETACH DATABASE src;")

    # 4. Watchlist
    conn_dst.execute("""
    CREATE TABLE watchlist (
        user_id TEXT DEFAULT 'default_user',
        symbol TEXT NOT NULL,
        created_at TEXT NOT NULL,
        PRIMARY KEY(user_id, symbol)
    );
    """)

    # Indexes
    conn_dst.execute("CREATE INDEX idx_price_symbol_date ON price_history (symbol, date DESC);")
    conn_dst.execute("CREATE INDEX idx_price_date ON price_history (date DESC);")
    conn_dst.execute("CREATE INDEX idx_signals_trigger_date ON signals (trigger_date DESC);")
    conn_dst.execute("CREATE INDEX idx_signals_pattern ON signals (pattern_type);")
    conn_dst.execute("CREATE INDEX idx_signals_symbol ON signals (symbol);")

    conn_dst.execute("VACUUM;")
    conn_dst.close()
    conn_src.close()

    raw_mb = round(os.path.getsize(dst_db) / 1024 / 1024, 2)
    print(f"Clean database created in {time.time() - start:.1f}s: {raw_mb} MB ({len(stocks_rows)} stocks, {len(signals_rows)} signals)")

    # Gzip compress with compresslevel=9
    with open(dst_db, "rb") as f_in, gzip.open(gz_path, "wb", compresslevel=9) as f_out:
        shutil.copyfileobj(f_in, f_out)

    os.remove(dst_db)
    gz_mb = round(os.path.getsize(gz_path) / 1024 / 1024, 2)
    print(f"Successfully packaged seed_history.db.gz: {gz_mb} MB (< 25 MB GitHub limit) in {time.time() - start:.1f}s")

if __name__ == "__main__":
    pack_seed()
