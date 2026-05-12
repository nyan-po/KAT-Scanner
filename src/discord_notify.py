"""
Discord webhook sender for KAT alert notifications.
"""
import logging
import requests

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


def send_alert(webhook_url: str, alert: dict) -> bool:
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
    price_str  = f"${price:.2f}"  if price   is not None else "N/A"
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

    try:
        resp = requests.post(
            webhook_url,
            json={"embeds": [embed]},
            timeout=10,
        )
        resp.raise_for_status()
        return True
    except Exception as e:
        logger.warning(f"Discord webhook failed for {ticker}: {e}")
        return False


def send_batch(webhook_url: str, triggered_alerts: list[dict]) -> int:
    """Send all triggered alerts; returns count of successful sends."""
    return sum(send_alert(webhook_url, a) for a in triggered_alerts)
