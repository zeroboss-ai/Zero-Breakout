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

def run_premarket_pipeline():
    """Broadcasts 8:45 AM IST Pre-Market Watchlist & Sector Radar to Telegram"""
    logger.info("Executing 8:45 AM IST Pre-Market Radar Pipeline...")
    try:
        from .telegram_service import format_and_broadcast_premarket_radar
        res = format_and_broadcast_premarket_radar()
        logger.info(f"Pre-Market Radar Broadcast Result: {res}")
        return res
    except Exception as e:
        logger.error(f"Error in Pre-Market Pipeline: {e}", exc_info=True)
        return {"error": str(e)}

def run_weekend_pipeline():
    """Broadcasts Sunday 11:00 AM IST Weekend Market Deep-Dive to Telegram"""
    logger.info("Executing Sunday 11:00 AM IST Weekend Deep-Dive Pipeline...")
    try:
        from .telegram_service import format_and_broadcast_weekend_digest
        res = format_and_broadcast_weekend_digest()
        logger.info(f"Weekend Deep-Dive Broadcast Result: {res}")
        return res
    except Exception as e:
        logger.error(f"Error in Weekend Pipeline: {e}", exc_info=True)
        return {"error": str(e)}

def start_scheduler():
    """
    Initializes and starts APScheduler:
    - Pre-Market Radar: 08:45 IST (03:15 UTC) Mon-Fri
    - Primary EOD Scan: 17:00 IST (5:00 PM IST / 11:30 UTC) Mon-Fri
    - Backup Confirmation Scan: 18:00 IST (6:00 PM IST / 12:30 UTC) Mon-Fri
    - Weekend Review: 11:00 IST (05:30 UTC) Sunday
    """
    if not scheduler.running:
        # 1. Pre-Market: 08:45 IST = 03:15 UTC Mon-Fri
        trigger_premarket = CronTrigger(day_of_week="mon-fri", hour=3, minute=15, timezone="UTC")
        scheduler.add_job(
            run_premarket_pipeline,
            trigger=trigger_premarket,
            id="premarket_radar_845am",
            name="Pre-Market Watchlist & Sector Radar (8:45 AM IST)",
            replace_existing=True
        )

        # 2. Primary EOD: 17:00 IST = 11:30 UTC Mon-Fri
        trigger_primary = CronTrigger(day_of_week="mon-fri", hour=11, minute=30, timezone="UTC")
        scheduler.add_job(
            run_daily_eod_pipeline,
            trigger=trigger_primary,
            id="daily_eod_scan_5pm",
            name="Daily NSE Bhavcopy & Pattern Scanner (5:00 PM IST)",
            replace_existing=True
        )

        # 3. Backup EOD: 18:00 IST = 12:30 UTC Mon-Fri
        trigger_backup = CronTrigger(day_of_week="mon-fri", hour=12, minute=30, timezone="UTC")
        scheduler.add_job(
            run_daily_eod_pipeline,
            trigger=trigger_backup,
            id="daily_eod_scan_6pm_backup",
            name="Daily NSE Bhavcopy Confirmation Scan (6:00 PM IST)",
            replace_existing=True
        )

        # 4. Weekend Deep-Dive: 11:00 IST = 05:30 UTC Sunday
        trigger_weekend = CronTrigger(day_of_week="sun", hour=5, minute=30, timezone="UTC")
        scheduler.add_job(
            run_weekend_pipeline,
            trigger=trigger_weekend,
            id="weekend_review_sunday_11am",
            name="Weekend Market Review & Setup Index (Sunday 11:00 AM IST)",
            replace_existing=True
        )

        # 5. Continuous Self-Healing Sync (Every 30 mins)
        scheduler.add_job(
            sync_missing_bhavcopies,
            trigger="interval",
            minutes=30,
            id="auto_catchup_sync_30m",
            name="Self-Healing Multi-Day Bhavcopy Sync (30 min interval)",
            replace_existing=True
        )

        scheduler.start()
        logger.info("Background scheduler started successfully (Interval 30m, Pre-Market 8:45 AM, EOD 5:00 PM & 6:00 PM, Sunday 11:00 AM IST).")

def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown()
        logger.info("Background scheduler stopped.")
