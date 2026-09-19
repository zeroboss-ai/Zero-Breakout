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
