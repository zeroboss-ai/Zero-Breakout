import os
import sys
import logging
from datetime import datetime, timezone, timedelta

# Ensure project root is in sys.path
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ZeroBreakout.AutoSync")

def run_auto_sync():
    from backend.database import init_db, get_connection
    from backend.seed_data import seed_database_if_empty
    from backend.data_fetcher import sync_missing_bhavcopies
    from backend.patterns.engine import pattern_engine
    import scripts.pack_seed as pack_script
    import json

    logger.info("Initializing database...")
    init_db()
    seed_database_if_empty()

    logger.info("Running Bhavcopy catch-up sync...")
    sync_res = sync_missing_bhavcopies()
    logger.info(f"Sync result: {sync_res}")

    # Always re-pack seed bundle if newest date in db is newer than seed date or if synced
    conn = get_connection()
    row = conn.execute("SELECT MAX(date) as max_date FROM price_history").fetchone()
    max_db_date = row["max_date"] if row else None
    
    logger.info(f"Database newest price history date: {max_db_date}")
    logger.info("Packaging fresh seed bundles for production deployment...")
    pack_script.pack_seed()

    # Update universe_seed.json
    stocks = [dict(r) for r in conn.execute('SELECT * FROM stocks WHERE market_cap_cr >= 2000 OR symbol IN (SELECT symbol FROM signals)').fetchall()]
    signals = [dict(r) for r in conn.execute('SELECT * FROM signals ORDER BY trigger_date DESC, id DESC').fetchall()]
    conn.close()

    json_path = os.path.join(root_dir, "backend", "seed_data", "universe_seed.json")
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump({'stocks': stocks, 'signals': signals}, f)
    logger.info(f"Updated universe_seed.json: {len(stocks)} stocks, {len(signals)} signals.")

if __name__ == "__main__":
    run_auto_sync()
