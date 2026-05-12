"""
Discord webhook sender for KAT alert notifications.
"""
import logging
import requests
from datetime import datetime

logger = logging.getLogger(__name__)

_CONDITION_META = {
    "price_below":    ("🔴", "dropped below",    0xEF5350),
    "price_above":    ("🟢", "broke above",       0x00C853),
    "day_chg_above":  ("🚀", "surged",            0x00C853),
    "day_chg_below":  ("📉", "sold off",          0xEF5350),
    "rel_vol_above":  ("🔥", "volume spike above", 0xFF9800),
}


def _fmt_threshold(condition: str, threshold: float) -> str:
    if "price" in condition:
        return f"${threshold:.2f}"
    if "chg" in condition:
        return f"{threshold:.1f}%"
    return f"{threshold:.1f}x"


def send_alert(webhook_url: str, alert: dict, ping_id: str = "") -> bool:
    """POST an embed to the Discord webhook. Returns True on success."""
    if not webhook_url:
        return False

    ticker  = alert["ticker"]
    cond    = alert["condition"]
    thresh  = float(alert["threshold"])
    desc    = alert.get("description", "")
    grade   = alert.get("projected_grade", "")
    q       = alert.get("quote", {})

    price   = q.get("price")
    day_chg = q.get("day_change_pct")
    rel_vol = q.get("rel_volume")

    emoji, verb, color = _CONDITION_META.get(cond, ("🔔", "triggered", 0x607D8B))
    thresh_str = _fmt_threshold(cond, thresh)
    price_str  = f"${price:.2f}"    if price   is not None else "N/A"
    chg_str    = f"{day_chg:+.1f}%" if day_chg is not None else "N/A"
    rvol_str   = f"{rel_vol:.1f}x"  if rel_vol is not None else "N/A"

    body = f"**{ticker}** {verb} {thresh_str}\n"
    if desc:
        body += f"_{desc}_\n"
    body += f"\nPrice: **{price_str}** | Day: **{chg_str}** | RelVol: **{rvol_str}**"
    if grade:
        body += f"\nProjected grade if setup completes: **{grade}**"

    embed = {
        "title":       f"{emoji} KAT Alert — {ticker}",
        "description": body,
        "color":       color,
        "footer":      {"text": "KAT Market Screener"},
        "timestamp":   alert.get("triggered_at"),
    }

    # content field is the only place Discord resolves mentions
    content = f"<@{ping_id}>" if ping_id.strip() else ""

    try:
        resp = requests.post(
            webhook_url,
            json={"content": content, "embeds": [embed]},
            timeout=10,
        )
        resp.raise_for_status()
        return True
    except Exception as e:
        logger.warning(f"Discord webhook failed for {ticker}: {e}")
        return False


def send_batch(webhook_url: str, triggered_alerts: list[dict], ping_id: str = "") -> int:
    """Send all triggered alerts; returns count of successful sends."""
    return sum(send_alert(webhook_url, a, ping_id=ping_id) for a in triggered_alerts)


def send_test(webhook_url: str) -> tuple[bool, str]:
    """Send a test embed to verify the webhook URL works. Returns (ok, message)."""
    if not webhook_url:
        return False, "No webhook URL configured."
    embed = {
        "title":       "🔔 KAT Alert — Test",
        "description": "**TEST** — your Discord webhook is connected correctly.\nReal alerts will look like this when a scenario triggers.",
        "color":       0x0288D1,
        "footer":      {"text": "KAT Market Screener"},
    }
    try:
        resp = requests.post(webhook_url, json={"embeds": [embed]}, timeout=10)
        resp.raise_for_status()
        return True, "Test message sent successfully!"
    except requests.HTTPError as e:
        return False, f"HTTP error {e.response.status_code}: {e.response.text[:200]}"
    except Exception as e:
        return False, str(e)


def send_scan_summary(
    webhook_url: str,
    results: list[dict],
    scan_type: str = "market",
    mode: str = "short_term",
    total_scanned: int = 0,
    ping_id: str = "",
) -> bool:
    """Send a formatted scan summary embed to Discord."""
    if not webhook_url or not results:
        return False

    lines = []
    for i, r in enumerate(results[:15], 1):
        ticker  = r.get("ticker", "")
        grade   = r.get("kat_grade", "?")
        score   = r.get("kat_score", 0)
        setup   = r.get("setup_type", "")
        action  = r.get("suggested_action", "")
        lines.append(f"{i}. **{ticker}** {grade} / {score} - {setup} ({action})")

    mode_label = "short_term" if mode == "short_term" else "long_term"
    description = (
        f"**{scan_type} / {mode_label}**\n\n"
        + "\n".join(lines)
        + f"\n\n**Scanned:** {total_scanned}   **Passing:** {len(results)}\n"
        + f"**Timestamp:** {datetime.now().strftime('%Y-%m-%dT%H:%M:%S')}"
    )

    top_grade = results[0].get("kat_grade", "C") if results else "C"
    color = (
        0x00C853 if top_grade in ("A+", "A", "A-") else
        0x0288D1 if top_grade in ("B+", "B", "B-") else
        0xF9A825
    )

    embed = {
        "title":       "📈 KAT Pre-Market Scan",
        "description": description,
        "color":       color,
        "footer":      {"text": "KAT Market Screener"},
    }

    content = f"<@{ping_id}>" if ping_id.strip() else ""

    try:
        resp = requests.post(
            webhook_url,
            json={"content": content, "embeds": [embed]},
            timeout=15,
        )
        resp.raise_for_status()
        return True
    except Exception as e:
        logger.warning(f"Discord scan summary failed: {e}")
        return False
    """Send a test embed to verify the webhook URL works. Returns (ok, message)."""
    if not webhook_url:
        return False, "No webhook URL configured."
    embed = {
        "title":       "🔔 KAT Alert — Test",
        "description": "**TEST** — your Discord webhook is connected correctly.\nReal alerts will look like this when a scenario triggers.",
        "color":       0x0288D1,
        "footer":      {"text": "KAT Market Screener"},
    }
    try:
        resp = requests.post(webhook_url, json={"embeds": [embed]}, timeout=10)
        resp.raise_for_status()
        return True, "Test message sent successfully!"
    except requests.HTTPError as e:
        return False, f"HTTP error {e.response.status_code}: {e.response.text[:200]}"
    except Exception as e:
        return False, str(e)
