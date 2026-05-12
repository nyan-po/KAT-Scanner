"""
Discord webhook notifications for KAT Market Screener alerts.
"""
import os
from datetime import datetime, timezone

import requests

WEBHOOK_ENV_KEY = "DISCORD_WEBHOOK_URL"

# Discord embed colors
_COLOR_ALERT = 0x00FF88   # green
_COLOR_BATCH = 0xFFAA00   # amber
_COLOR_TEST  = 0x5865F2   # Discord blurple
_COLOR_ERROR = 0xFF4444   # red


def _get_url(webhook_url: str = "") -> str:
    return webhook_url.strip() or os.getenv(WEBHOOK_ENV_KEY, "").strip()


def _post(payload: dict, webhook_url: str = "") -> bool:
    url = _get_url(webhook_url)
    if not url:
        return False
    try:
        r = requests.post(url, json=payload, timeout=10)
        return r.status_code in (200, 204)
    except Exception:
        return False


def send_alert(title: str, message: str, webhook_url: str = "") -> bool:
    """Send a single alert embed to Discord."""
    payload = {
        "embeds": [{
            "title": f"KAT Alert: {title}",
            "description": message,
            "color": _COLOR_ALERT,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "footer": {"text": "KAT Market Screener"},
        }]
    }
    return _post(payload, webhook_url)


def send_batch(alerts: list[dict], webhook_url: str = "") -> bool:
    """Send a batch of triggered alerts as a single Discord embed."""
    if not alerts:
        return True
    lines = []
    for a in alerts:
        ticker = a.get("ticker", "?")
        result = a.get("result", {})
        score = result.get("kat_score", "?")
        grade = result.get("kat_grade", "?")
        action = result.get("suggested_action", "?")
        price = result.get("price")
        price_str = f"${price:.2f}" if price else "N/A"
        lines.append(
            f"**{ticker}** — {price_str} | Score: {score} | Grade: {grade} | {action}"
        )
    payload = {
        "embeds": [{
            "title": f"KAT Alert Batch — {len(alerts)} triggered",
            "description": "\n".join(lines),
            "color": _COLOR_BATCH,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "footer": {"text": "KAT Market Screener"},
        }]
    }
    return _post(payload, webhook_url)


def send_test(webhook_url: str = "") -> bool:
    """Send a test notification to verify the webhook is configured correctly."""
    payload = {
        "embeds": [{
            "title": "KAT Market Screener — Test Notification",
            "description": "Your Discord webhook is connected and working correctly.",
            "color": _COLOR_TEST,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "footer": {"text": "KAT Market Screener"},
        }]
    }
    return _post(payload, webhook_url)
