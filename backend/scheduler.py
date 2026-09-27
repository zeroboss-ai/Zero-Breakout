import logging
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from .data_fetcher import fetch_nse_bhavcopy_for_date, process_and_save_bhavcopy, sync_missing_bhavcopies
from .patterns.engine import pattern_engine

logger = logging.getLogger("ZeroBreakout.Scheduler")

scheduler = BackgroundScheduler()

def run_daily_eod_data_sync():
    """
    Silent Background Ingestion (5:00 PM IST & 30-min intervals):
    1. Downloads missing Bhavcopies from NSE as soon as available
    2. Updates stock price history & ATH values
    3. Runs pattern engine across all 1,110+ scrips
    Does NOT send broadcast notifications (prevents duplicate alerts).
    """
    logger.info("Executing background Bhavcopy data sync & pattern scan...")
    try:
        sync_result = sync_missing_bhavcopies()
        logger.info(f"Background Sync Result: {sync_result}")
        final_results = sync_result.get("scan_results")
        if not final_results:
            final_results = pattern_engine.scan_all_stocks()
        return final_results
    except Exception as e:
        logger.error(f"Error in background data sync: {e}", exc_info=True)
        return {"error": str(e)}

def run_evening_eod_broadcast():
    """
    Consolidated Single Evening Notification Pipeline (6:30 PM IST):
    1. Syncs any missing Bhavcopies to guarantee latest data
    2. Broadcasts official Daily Breakout Digest to Telegram Channel (@ZeroBreakout)
    3. Dispatches Web/App Push Notifications with top ATH & 52WH breakouts to installed app users
    """
    logger.info("Executing 6:30 PM IST Evening Notification Pipeline (Telegram + App Push)...")
    results = {}
    try:
        # Step 1: Ensure latest market session data is ingested
        sync_result = sync_missing_bhavcopies()
        results["sync"] = sync_result

        # Step 2: Telegram EOD Broadcast
        try:
            from .telegram_service import format_and_broadcast_eod_alerts
            tg_res = format_and_broadcast_eod_alerts()
            results["telegram"] = tg_res
            logger.info(f"Telegram 6:30 PM Broadcast Result: {tg_res}")
        except Exception as tg_err:
            logger.warning(f"Telegram 6:30 PM broadcast notice: {tg_err}")
            results["telegram"] = {"error": str(tg_err)}

        # Step 3: App Push Notification Broadcast
        try:
            from .push_service import send_eod_push_notification
            push_res = send_eod_push_notification()
            results["push"] = push_res
            logger.info(f"App Push 6:30 PM Broadcast Result: {push_res}")
        except Exception as push_err:
            logger.warning(f"App Push 6:30 PM broadcast notice: {push_err}")
            results["push"] = {"error": str(push_err)}

        return results
    except Exception as e:
        logger.error(f"Error in 6:30 PM EOD notification pipeline: {e}", exc_info=True)
        return {"error": str(e)}

def run_premarket_pipeline():
    """
    Pre-Market Morning Radar Pipeline (8:45 AM IST):
    1. Broadcasts 8:45 AM Pre-Market Watchlist & Sector Radar to Telegram
    2. Sends App Push Notification to all traders for market open
    """
    logger.info("Executing 8:45 AM IST Pre-Market Radar Pipeline (Telegram + App Push)...")
    results = {}
    try:
        # Telegram broadcast
        try:
            from .telegram_service import format_and_broadcast_premarket_radar
            res = format_and_broadcast_premarket_radar()
            results["telegram"] = res
            logger.info(f"Pre-Market Radar Telegram Result: {res}")
        except Exception as tg_err:
            logger.warning(f"Pre-Market Telegram notice: {tg_err}")
            results["telegram"] = {"error": str(tg_err)}

        # App Push Notification
        try:
            from .push_service import send_premarket_push_notification
            push_res = send_premarket_push_notification()
            results["push"] = push_res
            logger.info(f"Pre-Market Push Result: {push_res}")
        except Exception as push_err:
            logger.warning(f"Pre-Market Push notice: {push_err}")
            results["push"] = {"error": str(push_err)}

        return results
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
    - Pre-Market Radar (Telegram + Push): 08:45 IST (03:15 UTC Mon-Fri)
    - Silent EOD Bhavcopy Ingestion: 17:00 IST (11:30 UTC Mon-Fri)
    - Single Consolidated Evening Broadcast (Telegram + Push): 18:30 IST (6:30 PM IST / 13:00 UTC Mon-Fri)
    - Weekend Review: 11:00 IST (05:30 UTC Sunday)
    - Self-Healing Sync: Every 30 minutes
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

        # 2. Silent EOD Data Fetch & Pattern Scan: 17:00 IST = 11:30 UTC Mon-Fri (Silent - no alerts)
        trigger_silent_eod = CronTrigger(day_of_week="mon-fri", hour=11, minute=30, timezone="UTC")
        scheduler.add_job(
            run_daily_eod_data_sync,
            trigger=trigger_silent_eod,
            id="daily_eod_silent_sync_5pm",
            name="Daily NSE Bhavcopy Ingest & Pattern Engine (5:00 PM IST - Silent)",
            replace_existing=True
        )

        # 3. Consolidated Evening Notification (Telegram + App Push): 18:30 IST = 13:00 UTC Mon-Fri
        trigger_evening_broadcast = CronTrigger(day_of_week="mon-fri", hour=13, minute=0, timezone="UTC")
        scheduler.add_job(
            run_evening_eod_broadcast,
            trigger=trigger_evening_broadcast,
            id="daily_eod_broadcast_630pm",
            name="Consolidated Evening Breakout Digest (6:30 PM IST - Telegram & App Push)",
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
        logger.info("Background scheduler started successfully (Interval 30m, Pre-Market 8:45 AM, Silent Sync 5:00 PM, Single Evening Alert 6:30 PM, Sunday 11:00 AM IST).")

def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown()
        logger.info("Background scheduler stopped.")
