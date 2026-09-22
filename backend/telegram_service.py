import os
import logging
import requests
from typing import Dict, Any, List, Optional
from datetime import datetime

logger = logging.getLogger("ZeroBreakout.TelegramService")

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHANNEL_ID = os.environ.get("TELEGRAM_CHANNEL_ID", "@ZeroBreakout").strip()

def send_telegram_message(
    message: str,
    channel_id: Optional[str] = None,
    bot_token: Optional[str] = None,
    parse_mode: str = "HTML"
) -> Dict[str, Any]:
    """
    Sends a message to the ZeroBreakout Telegram channel or specified chat_id.
    """
    token = bot_token or TELEGRAM_BOT_TOKEN or os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    target_chat = channel_id or TELEGRAM_CHANNEL_ID or os.environ.get("TELEGRAM_CHANNEL_ID", "@ZeroBreakout").strip()

    if not token:
        logger.warning("Telegram broadcast skipped: TELEGRAM_BOT_TOKEN is not configured.")
        return {"status": "skipped", "message": "TELEGRAM_BOT_TOKEN environment variable not set."}

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": target_chat,
        "text": message,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True
    }

    try:
        response = requests.post(url, json=payload, timeout=10)
        data = response.json()
        if response.status_code == 200 and data.get("ok"):
            logger.info(f"Successfully broadcasted message to Telegram channel {target_chat}")
            return {"status": "success", "result": data}
        else:
            logger.error(f"Failed to send Telegram message: {data}")
            return {"status": "error", "detail": data}
    except Exception as e:
        logger.error(f"Exception sending Telegram message: {e}")
        return {"status": "error", "detail": str(e)}

def format_and_broadcast_eod_alerts() -> Dict[str, Any]:
    """
    Generates an automated daily post-market breakout digest and broadcasts it to Telegram.
    Syncs missing Bhavcopies first to guarantee fresh data for the latest trading session.
    """
    from .data_fetcher import sync_missing_bhavcopies
    from .database import get_latest_signals, get_connection
    from datetime import timezone, timedelta

    # 1. Pre-broadcast sync check: Ensure today's / latest Bhavcopy is downloaded
    try:
        sync_res = sync_missing_bhavcopies()
        logger.info(f"Pre-broadcast catch-up sync completed: {sync_res}")
    except Exception as sync_err:
        logger.warning(f"Notice during pre-broadcast sync: {sync_err}")

    conn = get_connection()
    row = conn.execute("SELECT MAX(date) as max_date FROM price_history").fetchone()
    latest_market_date = row["max_date"] if row and row["max_date"] else None
    conn.close()

    if not latest_market_date:
        logger.warning("No price history available for Telegram broadcast.")
        return {"status": "skipped", "message": "No price history available."}

    # Format actual market session date
    try:
        d_obj = datetime.strptime(latest_market_date, "%Y-%m-%d")
        date_display = d_obj.strftime("%d %b %Y")
    except Exception:
        date_display = latest_market_date

    # Fetch signals matching the latest trading session
    ath_signals = get_latest_signals(pattern_type="All-Time High Breakout", limit=12)
    ath_fresh = [s for s in ath_signals if s.get("trigger_date") == latest_market_date or s.get("percent_vs_pivot", -99) >= -1.5]

    fth_signals = get_latest_signals(pattern_type="52-Week High Breakout", limit=12)
    fth_fresh = [s for s in fth_signals if s.get("trigger_date") == latest_market_date or s.get("percent_vs_pivot", -99) >= -1.5]

    ipo_signals = get_latest_signals(pattern_type="IPO Breakout", limit=6)
    ipo_fresh = [s for s in ipo_signals if s.get("trigger_date") == latest_market_date or s.get("percent_vs_pivot", -99) >= -1.5]

    near_52w = get_latest_signals(pattern_type="Near 52-Week High", limit=6)

    if not ath_fresh and not fth_fresh and not ipo_fresh and not near_52w:
        logger.info("No active breakout signals found for today's Telegram broadcast.")
        return {"status": "skipped", "message": "No active signals for latest session."}

    lines = [
        f"⚡ <b>ZeroBreakout Daily Market Digest</b> — <i>{date_display}</i>\n",
        "EOD Market Structure & Momentum Breakouts detected by algorithmic scanner:\n"
    ]

    # 1. ATH Breakouts
    if ath_fresh:
        lines.append("🚀 <b>ALL-TIME HIGH BREAKOUTS:</b>")
        for s in ath_fresh[:4]:
            sym = s.get("symbol", "")
            name = s.get("company_name", sym)
            price = s.get("current_price", 0)
            chg = s.get("change_pct", 0)
            sign = "+" if chg > 0 else ""
            lines.append(f"• <b>{sym}</b> ({name}) — ₹{price:,.2f} (<code>{sign}{chg:.2f}%</code>)")
            lines.append(f"  🔗 <a href='https://www.zerobreakout.in/stock/{sym}'>View Chart & Setup</a>")
        lines.append("")

    # 2. 52-Week High Breakouts
    if fth_fresh:
        lines.append("🔥 <b>52-WEEK HIGH BREAKOUTS:</b>")
        for s in fth_fresh[:4]:
            sym = s.get("symbol", "")
            price = s.get("current_price", 0)
            chg = s.get("change_pct", 0)
            sign = "+" if chg > 0 else ""
            lines.append(f"• <b>{sym}</b> — ₹{price:,.2f} (<code>{sign}{chg:.2f}%</code>) | <a href='https://www.zerobreakout.in/stock/{sym}'>Chart</a>")
        lines.append("")

    # 3. IPO Breakouts
    if ipo_fresh:
        lines.append("🌟 <b>FRESH IPO BREAKOUTS:</b>")
        for s in ipo_fresh[:3]:
            sym = s.get("symbol", "")
            price = s.get("current_price", 0)
            chg = s.get("change_pct", 0)
            sign = "+" if chg > 0 else ""
            lines.append(f"• <b>{sym}</b> — ₹{price:,.2f} (<code>{sign}{chg:.2f}%</code>) | <a href='https://www.zerobreakout.in/stock/{sym}'>Chart</a>")
        lines.append("")

    # 4. If fewer than 3 breakouts, show Near-Pivot Leaders
    if len(ath_fresh) + len(fth_fresh) < 3 and near_52w:
        lines.append("🎯 <b>PIVOT WATCHLIST (Near 52W / ATH Resistance):</b>")
        for s in near_52w[:3]:
            sym = s.get("symbol", "")
            price = s.get("current_price", 0)
            pivot = s.get("pivot_price", 0)
            pct = s.get("percent_vs_pivot", 0)
            lines.append(f"• <b>{sym}</b> — CMP ₹{price:,.2f} | Pivot ₹{pivot:,.2f} (<code>{pct:+.1f}% vs Pivot</code>)")
        lines.append("")

    lines.append("📊 <b>Explore full 1,110+ stock scanner:</b> https://www.zerobreakout.in")
    lines.append("\n<i>ℹ️ Strictly for educational & technical analysis purposes. Not SEBI registered advice.</i>")

    message_text = "\n".join(lines)
    return send_telegram_message(message_text)

def format_and_broadcast_premarket_radar() -> Dict[str, Any]:
    """
    Generates a pre-market watchlist and sector radar bulletin at 8:45 AM IST Mon-Fri.
    """
    from .database import get_latest_signals, get_all_active_symbols, get_connection
    from datetime import timezone, timedelta

    ist_now = datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)
    date_display = ist_now.strftime("%a, %d %b %Y")

    # Fetch candidate stocks consolidating near pivot or with active momentum
    near_ath = get_latest_signals(pattern_type="Near 52-Week High", limit=5)
    range_bo = get_latest_signals(pattern_type="Range Breakout", limit=3)

    # Calculate top sector momentum
    conn = get_connection()
    sector_rows = conn.execute("""
        SELECT st.sector, COUNT(*) as cnt 
        FROM signals s
        JOIN stocks st ON s.symbol = st.symbol
        WHERE st.sector != 'General' AND st.sector != ''
        GROUP BY st.sector 
        ORDER BY cnt DESC LIMIT 3;
    """).fetchall()
    conn.close()

    lines = [
        f"🌅 <b>ZeroBreakout Pre-Market Radar</b> — <i>{date_display}</i>\n",
        "Key breakout candidates & market structures on watch for today's market open:\n"
    ]

    if near_ath:
        lines.append("🎯 <b>PIVOT WATCHLIST (Near 52W / ATH Resistance):</b>")
        for s in near_ath[:4]:
            sym = s.get("symbol", "")
            pivot = s.get("pivot_price", 0)
            curr = s.get("current_price", 0)
            pct = s.get("percent_vs_pivot", 0)
            lines.append(f"• <b>{sym}</b> — CMP ₹{curr:,.2f} | Pivot ₹{pivot:,.2f} (<code>{pct:+.1f}% vs Pivot</code>)")
            lines.append(f"  🔗 <a href='https://www.zerobreakout.in/stock/{sym}'>Open Chart</a>")
        lines.append("")

    if sector_rows:
        lines.append("🔥 <b>SECTOR BREAKOUT DENSITY:</b>")
        for r in sector_rows:
            lines.append(f"• <b>{r['sector']}</b> ({r['cnt']} active setups)")
        lines.append("")

    lines.append("💡 <i>Tip: Look for volume surge > 2x average on 15m opening range breakout.</i>")
    lines.append("📊 <b>Live Terminal:</b> https://www.zerobreakout.in")
    lines.append("\n<i>ℹ️ Strictly for educational & technical analysis purposes. Not financial advice.</i>")

    message_text = "\n".join(lines)
    return send_telegram_message(message_text)

def format_and_broadcast_weekend_digest() -> Dict[str, Any]:
    """
    Generates a weekend deep-dive recap & weekly setup index at 11:00 AM IST Sundays.
    """
    from .database import get_latest_signals, get_all_active_symbols, get_connection
    from datetime import timezone, timedelta

    ist_now = datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)
    date_display = ist_now.strftime("%d %b %Y")

    ath_signals = get_latest_signals(pattern_type="All-Time High Breakout", limit=6)
    fresh_signals = get_latest_signals(pattern_type="Fresh Breakout", limit=6)
    stocks = get_all_active_symbols()

    lines = [
        f"☕ <b>ZeroBreakout Weekend Market Review</b> — <i>{date_display}</i>\n",
        f"Comprehensive technical structure analysis across <b>{len(stocks):,} NSE stocks & IPOs</b>:\n"
    ]

    if ath_signals:
        lines.append("🏆 <b>TOP ALL-TIME HIGH LEADERS:</b>")
        for s in ath_signals[:4]:
            sym = s.get("symbol", "")
            name = s.get("company_name", sym)
            price = s.get("current_price", 0)
            chg = s.get("change_pct", 0)
            lines.append(f"• <b>{sym}</b> ({name}) — ₹{price:,.2f} (<code>{chg:+.2f}%</code>) | <a href='https://www.zerobreakout.in/stock/{sym}'>Setup</a>")
        lines.append("")

    if fresh_signals:
        lines.append("⚡ <b>FRESH BREAKOUT SETUPS FOR UPCOMING WEEK:</b>")
        for s in fresh_signals[:4]:
            sym = s.get("symbol", "")
            price = s.get("current_price", 0)
            pat = s.get("pattern_type", "")
            lines.append(f"• <b>{sym}</b> — {pat} at ₹{price:,.2f} | <a href='https://www.zerobreakout.in/stock/{sym}'>Chart</a>")
        lines.append("")

    lines.append("🔍 <b>Scan & Filter 1,110+ Institutional Charts:</b> https://www.zerobreakout.in")
    lines.append("\n<i>ℹ️ Strictly for educational & technical analysis purposes. Not SEBI registered.</i>")

    message_text = "\n".join(lines)
    return send_telegram_message(message_text)

def handle_telegram_incoming_update(update: Dict[str, Any]) -> None:
    """
    Processes interactive user commands sent directly to the Telegram bot:
    /start, /help, /stock <SYM>, /fresh, /ath, /ipo, /stats
    """
    message = update.get("message") or update.get("edited_message")
    if not message:
        return

    chat_id = message.get("chat", {}).get("id")
    text = str(message.get("text", "")).strip()
    if not chat_id or not text:
        return

    from .database import get_stock_setup, get_latest_signals, get_all_active_symbols

    text_lower = text.lower()

    # 1. /start or /help
    if text_lower in ["/start", "/help", "help", "hi", "hello"]:
        reply = (
            "🤖 <b>Welcome to ZeroBreakout Bot!</b>\n\n"
            "I am your automated NSE Breakout Scanner assistant.\n\n"
            "<b>Available Commands:</b>\n"
            "• <code>/stock RELIANCE</code> — Get instant technical setup & ATH status\n"
            "• <code>/fresh</code> — Today's Fresh Breakout triggers\n"
            "• <code>/ath</code> — Top All-Time High Breakouts\n"
            "• <code>/ipo</code> — Fresh Mainboard IPO Breakouts\n"
            "• <code>/stats</code> — Scanner metrics & tracked universe\n\n"
            "🌐 <b>Interactive Web Terminal:</b> https://www.zerobreakout.in"
        )
        send_telegram_message(reply, channel_id=str(chat_id))
        return

    # 2. /fresh
    if text_lower.startswith("/fresh"):
        signals = get_latest_signals(pattern_type="Fresh Breakout", limit=5)
        if not signals:
            send_telegram_message("No fresh breakout triggers found today.", channel_id=str(chat_id))
            return
        lines = ["⚡ <b>TODAY'S FRESH BREAKOUTS:</b>\n"]
        for s in signals:
            sym = s.get("symbol", "")
            chg = s.get("change_pct", 0)
            lines.append(f"• <b>{sym}</b> ({s.get('pattern_type')}) — ₹{s.get('current_price', 0):,.2f} (<code>{chg:+.2f}%</code>)")
            lines.append(f"  🔗 https://www.zerobreakout.in/stock/{sym}")
        send_telegram_message("\n".join(lines), channel_id=str(chat_id))
        return

    # 3. /ath
    if text_lower.startswith("/ath"):
        signals = get_latest_signals(pattern_type="All-Time High Breakout", limit=5)
        if not signals:
            send_telegram_message("No ATH breakout triggers found.", channel_id=str(chat_id))
            return
        lines = ["🚀 <b>ALL-TIME HIGH BREAKOUTS:</b>\n"]
        for s in signals:
            sym = s.get("symbol", "")
            chg = s.get("change_pct", 0)
            lines.append(f"• <b>{sym}</b> — ₹{s.get('current_price', 0):,.2f} (<code>{chg:+.2f}%</code>)")
            lines.append(f"  🔗 https://www.zerobreakout.in/stock/{sym}")
        send_telegram_message("\n".join(lines), channel_id=str(chat_id))
        return

    # 4. /ipo
    if text_lower.startswith("/ipo"):
        signals = get_latest_signals(pattern_type="IPO Breakout", limit=5)
        if not signals:
            send_telegram_message("No IPO breakout triggers found.", channel_id=str(chat_id))
            return
        lines = ["🌟 <b>MAINBOARD IPO BREAKOUTS:</b>\n"]
        for s in signals:
            sym = s.get("symbol", "")
            lines.append(f"• <b>{sym}</b> — ₹{s.get('current_price', 0):,.2f} | https://www.zerobreakout.in/stock/{sym}")
        send_telegram_message("\n".join(lines), channel_id=str(chat_id))
        return

    # 5. /stats
    if text_lower.startswith("/stats"):
        stocks = get_all_active_symbols()
        signals = get_latest_signals(limit=500)
        reply = (
            f"📊 <b>ZeroBreakout Scanner Stats:</b>\n"
            f"• <b>Tracked Stocks & IPOs:</b> {len(stocks):,}\n"
            f"• <b>Active Breakout Signals:</b> {len(signals):,}\n"
            f"• <b>Engine:</b> Automated EOD Bhavcopy Ingestion + Modular Detectors\n\n"
            f"🌐 https://www.zerobreakout.in"
        )
        send_telegram_message(reply, channel_id=str(chat_id))
        return

    # 6. /stock <SYMBOL> or direct SYMBOL lookup (e.g. RELIANCE)
    clean_sym = text.replace("/stock", "").replace("/", "").strip().upper()
    if clean_sym:
        setup = get_stock_setup(clean_sym)
        if setup:
            sym = setup.get("symbol")
            name = setup.get("company_name", sym)
            price = setup.get("current_price", 0)
            chg = setup.get("change_pct", 0)
            ath = setup.get("all_time_high", 0)
            ath_date = setup.get("ath_date", "N/A")
            sig = setup.get("latest_signal")
            
            sig_text = f"⚡ <b>Active Pattern:</b> {sig['pattern_type']} (Pivot: ₹{sig.get('pivot_price', 0):,.2f})" if sig else "No active breakout pattern today."

            reply = (
                f"📈 <b>{sym}</b> — <i>{name}</i>\n"
                f"• <b>Current Price:</b> ₹{price:,.2f} (<code>{chg:+.2f}%</code>)\n"
                f"• <b>All-Time High:</b> ₹{ath:,.2f} <i>({ath_date})</i>\n"
                f"• {sig_text}\n\n"
                f"📊 <b>Full Candlestick Chart & AI Analysis:</b>\n"
                f"https://www.zerobreakout.in/stock/{sym}"
            )
            send_telegram_message(reply, channel_id=str(chat_id))
            return
        else:
            send_telegram_message(f"Stock symbol <b>{clean_sym}</b> not found. Try searching by NSE ticker like <code>/stock RELIANCE</code> or <code>/stock TRENT</code>.", channel_id=str(chat_id))

