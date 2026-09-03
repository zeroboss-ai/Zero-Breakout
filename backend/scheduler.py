import logging
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from .data_fetcher import fetch_nse_bhavcopy_for_date, process_and_save_bhavcopy
from .patterns.engine import pattern_engine

logger = logging.getLogger("ZeroBreakout.Scheduler")

scheduler = BackgroundScheduler()

def run_daily_eod_pipeline():
    """
    Automated Daily Pipeline:
    1. Downloads Daily Bhavcopy from NSE (~4:15-5:00 PM IST)
    2. Updates 5-year price history and stock all-time highs
    3. Executes modular pattern detection scan across all stocks and IPOs
    4. Persists all signals to the signals table for instantaneous UI access
    """
    now = datetime.now()
    today_str = now.strftime("%Y-%m-%d")
    logger.info(f"[{today_str}] Running Daily EOD Bhavcopy & Pattern Pipeline (5:00 PM IST)...")

    try:
        # Step 1: Fetch and save today's Bhavcopy
        df = fetch_nse_bhavcopy_for_date(now)
        if df is not None and not df.empty:
            saved_count = process_and_save_bhavcopy(df, today_str)
            logger.info(f"Successfully processed {saved_count} records from today's Bhavcopy.")
        else:
            logger.warning(f"Bhavcopy not yet published for {today_str}. Running pattern scan on latest available market candles.")

        # Step 2: Run Pattern Scan across all stocks & IPOs
        scan_results = pattern_engine.scan_all_stocks()
        logger.info(f"Daily Pattern Scan completed: {scan_results}")
        return scan_results

    except Exception as e:
        logger.error(f"Error executing daily EOD pipeline: {e}", exc_info=True)
        return {"error": str(e)}

def start_scheduler():
    """
    Initializes and starts APScheduler:
    - Primary EOD Scan: 17:00 IST (5:00 PM IST / 11:30 UTC) Mon-Fri
    - Backup Confirmation Scan: 18:00 IST (6:00 PM IST / 12:30 UTC) Mon-Fri
    """
    if not scheduler.running:
        # Primary: 17:00 IST = 11:30 UTC
        trigger_primary = CronTrigger(day_of_week="mon-fri", hour=11, minute=30, timezone="UTC")
        scheduler.add_job(
            run_daily_eod_pipeline,
            trigger=trigger_primary,
            id="daily_eod_scan_5pm",
            name="Daily NSE Bhavcopy & Pattern Scanner (5:00 PM IST)",
            replace_existing=True
        )

        # Backup: 18:00 IST = 12:30 UTC
        trigger_backup = CronTrigger(day_of_week="mon-fri", hour=12, minute=30, timezone="UTC")
        scheduler.add_job(
            run_daily_eod_pipeline,
            trigger=trigger_backup,
            id="daily_eod_scan_6pm_backup",
            name="Daily NSE Bhavcopy Confirmation Scan (6:00 PM IST)",
            replace_existing=True
        )

        scheduler.start()
        logger.info("Background daily EOD scheduler started successfully (runs at 5:00 PM & 6:00 PM IST Mon-Fri).")

def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown()
        logger.info("Background scheduler stopped.")
