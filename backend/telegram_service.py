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
    """
    from .database import get_latest_signals, get_connection
    from datetime import timezone, timedelta

    ist_now = datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)
    date_display = ist_now.strftime("%d %b %Y")

    # Fetch fresh signals
    ath_signals = get_latest_signals(pattern_type="All-Time High Breakout", limit=5)
    fth_signals = get_latest_signals(pattern_type="52-Week High Breakout", limit=5)
    ipo_signals = get_latest_signals(pattern_type="IPO Breakout", limit=3)

    if not ath_signals and not fth_signals:
        logger.info("No fresh breakout signals found for today's Telegram broadcast.")
        return {"status": "skipped", "message": "No signals to broadcast."}

    lines = [
        f"⚡ <b>ZeroBreakout Daily Market Digest</b> — <i>{date_display}</i>\n",
        "Market Structure & Momentum Breakouts detected by algorithmic scanner:\n"
    ]

    # 1. ATH Breakouts
    if ath_signals:
        lines.append("🚀 <b>ALL-TIME HIGH BREAKOUTS:</b>")
        for s in ath_signals[:4]:
            sym = s.get("symbol", "")
            name = s.get("company_name", sym)
            price = s.get("current_price", 0)
            chg = s.get("change_pct", 0)
            sign = "+" if chg > 0 else ""
            lines.append(f"• <b>{sym}</b> ({name}) — ₹{price:,.2f} (<code>{sign}{chg:.2f}%</code>)")
            lines.append(f"  🔗 <a href='https://www.zerobreakout.in/stock/{sym}'>View Chart & Setup</a>")
        lines.append("")

    # 2. 52-Week High Breakouts
    if fth_signals:
        lines.append("🔥 <b>52-WEEK HIGH BREAKOUTS:</b>")
        for s in fth_signals[:4]:
            sym = s.get("symbol", "")
            price = s.get("current_price", 0)
            chg = s.get("change_pct", 0)
            sign = "+" if chg > 0 else ""
            lines.append(f"• <b>{sym}</b> — ₹{price:,.2f} (<code>{sign}{chg:.2f}%</code>) | <a href='https://www.zerobreakout.in/stock/{sym}'>Chart</a>")
        lines.append("")

    # 3. IPO Breakouts
    if ipo_signals:
        lines.append("🌟 <b>FRESH IPO BREAKOUTS:</b>")
        for s in ipo_signals[:3]:
            sym = s.get("symbol", "")
            price = s.get("current_price", 0)
            chg = s.get("change_pct", 0)
            sign = "+" if chg > 0 else ""
            lines.append(f"• <b>{sym}</b> — ₹{price:,.2f} (<code>{sign}{chg:.2f}%</code>) | <a href='https://www.zerobreakout.in/stock/{sym}'>Chart</a>")
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

