import logging
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from .data_fetcher import fetch_nse_bhavcopy_for_date, process_and_save_bhavcopy, sync_missing_bhavcopies
from .patterns.engine import pattern_engine

logger = logging.getLogger("ZeroBreakout.Scheduler")

scheduler = BackgroundScheduler()

def run_daily_eod_pipeline():
    """
    Automated Daily Pipeline:
    1. Runs multi-day catch-up engine to download all missing Bhavcopies up to today
    2. Updates price history and stock all-time highs
    3. Executes pattern detection scan across all stocks and IPOs
    4. Persists all signals to the signals table for instantaneous UI access
    """
    logger.info("Executing EOD Bhavcopy & Pattern Pipeline...")
    try:
        sync_result = sync_missing_bhavcopies()
        logger.info(f"EOD Pipeline Sync Result: {sync_result}")
        final_results = sync_result.get("scan_results")
        if not final_results:
            # If already up to date, run quick pattern scan to ensure fresh state
            final_results = pattern_engine.scan_all_stocks()
            logger.info(f"EOD Pattern Scan complete: {final_results}")

        # Step 5: Broadcast EOD Breakout Digest to Telegram Channel (if configured)
        try:
            from .telegram_service import format_and_broadcast_eod_alerts
            tg_res = format_and_broadcast_eod_alerts()
            logger.info(f"Telegram EOD Broadcast Result: {tg_res}")
        except Exception as tg_err:
            logger.warning(f"Telegram EOD broadcast notice: {tg_err}")

        return final_results
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
