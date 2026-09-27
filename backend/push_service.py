import os
import json
import logging
import base64
from typing import Dict, Any, List, Optional
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization
from pywebpush import webpush, WebPushException

from .database import (
    save_push_subscription,
    get_all_push_subscriptions,
    delete_push_subscription,
    get_latest_signals,
    get_connection,
    DATA_DIR,
    ensure_data_dir
)

logger = logging.getLogger("ZeroBreakout.PushService")

VAPID_FILE = os.path.join(DATA_DIR, "vapid_keys.json")
VAPID_CLAIM_EMAIL = os.environ.get("VAPID_CLAIM_EMAIL", "mailto:zerobossai@gmail.com")

def _init_vapid_keys():
    """Loads existing VAPID keys or creates a persistent EC keypair."""
    ensure_data_dir()
    
    # 1. Check environment variables first
    env_pub = os.environ.get("VAPID_PUBLIC_KEY", "").strip()
    env_priv = os.environ.get("VAPID_PRIVATE_KEY", "").strip()
    if env_pub and env_priv:
        return {"public_key": env_pub, "private_key": env_priv}

    # 2. Check local persistent key file
    if os.path.isfile(VAPID_FILE):
        try:
            with open(VAPID_FILE, "r", encoding="utf-8") as f:
                keys = json.load(f)
                if keys.get("public_key") and keys.get("private_key"):
                    return keys
        except Exception as e:
            logger.warning(f"Error reading {VAPID_FILE}: {e}")

    # 3. Generate new EC SECP256R1 VAPID keypair
    try:
        curve = ec.SECP256R1()
        private_key = ec.generate_private_key(curve)
        public_key = private_key.public_key()

        raw_pub = public_key.public_bytes(
            encoding=serialization.Encoding.X962,
            format=serialization.PublicFormat.UncompressedPoint
        )
        b64_pub = base64.urlsafe_b64encode(raw_pub).decode('utf-8').rstrip('=')

        priv_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        ).decode('utf-8')

        keys = {"public_key": b64_pub, "private_key": priv_pem}
        with open(VAPID_FILE, "w", encoding="utf-8") as f:
            json.dump(keys, f, indent=2)

        logger.info("Generated and saved new persistent VAPID keypair.")
        return keys
    except Exception as e:
        logger.error(f"Failed to generate VAPID keypair: {e}")
        return {"public_key": "", "private_key": ""}

_VAPID = _init_vapid_keys()

def get_vapid_public_key() -> str:
    """Returns the VAPID public key string for frontend Web Push subscriptions."""
    return _VAPID.get("public_key", "")

def register_subscription(sub_data: Dict[str, Any], user_id: Optional[str] = None) -> bool:
    """
    Saves a subscription object from the frontend navigator.serviceWorker.pushManager.
    Expected sub_data: {"endpoint": "...", "keys": {"p256dh": "...", "auth": "..."}}
    """
    endpoint = sub_data.get("endpoint")
    keys = sub_data.get("keys", {})
    p256dh = keys.get("p256dh")
    auth = keys.get("auth")

    if not endpoint or not p256dh or not auth:
        logger.warning("Invalid subscription data received for Web Push.")
        return False

    return save_push_subscription(endpoint=endpoint, p256dh=p256dh, auth=auth, user_id=user_id)

def unregister_subscription(endpoint: str) -> bool:
    """Deletes an endpoint from the database."""
    return delete_push_subscription(endpoint)

def broadcast_push(
    title: str,
    body: str,
    url: str = "/",
    tag: str = "zerobreakout-alert",
    icon: str = "/static/assets/icon-192.png",
    badge: str = "/static/assets/icon-192.png"
) -> Dict[str, Any]:
    """
    Broadcasts a Web Push notification to all registered app/browser devices.
    Automatically purges expired/unsubscribed endpoints (HTTP 410 / 404).
    """
    private_key = _VAPID.get("private_key")
    if not private_key:
        logger.warning("Cannot broadcast push: VAPID private key is missing.")
        return {"status": "error", "message": "VAPID key not configured"}

    subscriptions = get_all_push_subscriptions()
    if not subscriptions:
        logger.info("No active push subscriptions to broadcast.")
        return {"status": "ok", "delivered": 0, "total": 0}

    payload = json.dumps({
        "title": title,
        "body": body,
        "icon": icon,
        "badge": badge,
        "url": url,
        "tag": tag,
        "timestamp": int(datetime.utcnow().timestamp() * 1000)
    })

    vapid_claims = {
        "sub": VAPID_CLAIM_EMAIL
    }

    delivered = 0
    failed = 0
    cleaned = 0

    for sub in subscriptions:
        sub_info = {
            "endpoint": sub["endpoint"],
            "keys": {
                "p256dh": sub["p256dh"],
                "auth": sub["auth"]
            }
        }
        try:
            webpush(
                subscription_info=sub_info,
                data=payload,
                vapid_private_key=private_key,
                vapid_claims=vapid_claims,
                ttl=86400 # 24 hours
            )
            delivered += 1
        except WebPushException as ex:
            failed += 1
            # HTTP 404 or 410 indicates endpoint is no longer valid or unsubscribed
            status_code = getattr(ex.response, 'status_code', None) if ex.response else None
            if status_code in [404, 410]:
                delete_push_subscription(sub["endpoint"])
                cleaned += 1
                logger.info(f"Purged expired push endpoint: {sub['endpoint'][:40]}...")
            else:
                logger.warning(f"WebPush error ({status_code}): {ex}")
        except Exception as e:
            failed += 1
            logger.warning(f"Unexpected WebPush exception: {e}")

    logger.info(f"Push broadcast '{title}': delivered={delivered}, failed={failed}, cleaned={cleaned}")
    return {"status": "ok", "delivered": delivered, "failed": failed, "total": len(subscriptions)}

def send_eod_push_notification() -> Dict[str, Any]:
    """
    Generates and broadcasts the evening EOD Breakout notification to all App users.
    """
    conn = get_connection()
    row = conn.execute("SELECT MAX(date) as max_date FROM price_history").fetchone()
    latest_market_date = row["max_date"] if row and row["max_date"] else None
    conn.close()

    ath_signals = get_latest_signals(pattern_type="All-Time High Breakout", limit=8)
    ath_fresh = [s for s in ath_signals if s.get("trigger_date") == latest_market_date or s.get("percent_vs_pivot", -99) >= -1.5]

    fth_signals = get_latest_signals(pattern_type="52-Week High Breakout", limit=8)
    fth_fresh = [s for s in fth_signals if s.get("trigger_date") == latest_market_date or s.get("percent_vs_pivot", -99) >= -1.5]

    ipo_signals = get_latest_signals(pattern_type="IPO Breakout", limit=4)
    ipo_fresh = [s for s in ipo_signals if s.get("trigger_date") == latest_market_date or s.get("percent_vs_pivot", -99) >= -1.5]

    sample_stocks = []
    for s in ath_fresh[:2] + fth_fresh[:2] + ipo_fresh[:1]:
        sym = s.get("symbol")
        if sym and sym not in sample_stocks:
            sample_stocks.append(sym)

    total_fresh = len(ath_fresh) + len(fth_fresh) + len(ipo_fresh)

    if total_fresh > 0 and sample_stocks:
        stocks_str = ", ".join(sample_stocks[:3])
        title = f"⚡ {total_fresh} New Breakouts Detected!"
        body = f"🚀 Top Setups: {stocks_str}. Tap to view candlestick charts & AI setups."
    else:
        title = "⚡ ZeroBreakout Market Scan Complete"
        body = "Today's NSE Bhavcopy processed. Tap to explore active breakout setups."

    return broadcast_push(
        title=title,
        body=body,
        url="/",
        tag="eod-breakouts-alert"
    )

def send_premarket_push_notification() -> Dict[str, Any]:
    """
    Generates and broadcasts 8:45 AM Pre-Market Watchlist notification to all App users.
    """
    title = "🌅 ZeroBreakout Pre-Market Radar"
    body = "Morning index pivot levels & top momentum setups ready for market open."
    return broadcast_push(
        title=title,
        body=body,
        url="/",
        tag="premarket-radar-alert"
    )
