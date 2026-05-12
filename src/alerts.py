"""
Scenario-based alert system for the KAT watchlist.
Stores alerts in alerts.json with condition, threshold, and trigger state.
"""
import json
import uuid
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

ALERTS_PATH = Path("alerts.json")

# Human-readable labels for the UI
CONDITION_LABELS = {
    "price_below":    "Price drops below $",
    "price_above":    "Price breaks above $",
    "day_chg_above":  "Day change exceeds +%",
    "day_chg_below":  "Day change drops below -%",
    "rel_vol_above":  "Rel volume exceeds x",
}


def _load_raw() -> dict:
    if not ALERTS_PATH.exists():
        return {"webhook_url": "", "alerts": []}
    try:
        return json.loads(ALERTS_PATH.read_text())
    except Exception:
        return {"webhook_url": "", "alerts": []}


def _save_raw(data: dict):
    ALERTS_PATH.write_text(json.dumps(data, indent=2, default=str))


def load_alerts() -> list[dict]:
    return _load_raw().get("alerts", [])


def load_webhook_url() -> str:
    return _load_raw().get("webhook_url", "")


def load_ping_id() -> str:
    return _load_raw().get("ping_id", "")


def save_ping_id(ping_id: str):
    data = _load_raw()
    data["ping_id"] = ping_id.strip()
    _save_raw(data)


def save_webhook_url(url: str):
    data = _load_raw()
    data["webhook_url"] = url.strip()
    _save_raw(data)


def add_alert(
    ticker: str,
    condition: str,
    threshold: float,
    description: str = "",
    projected_grade: str = "",
) -> list[dict]:
    data = _load_raw()
    alert = {
        "id":              str(uuid.uuid4())[:8],
        "ticker":          ticker.upper(),
        "condition":       condition,
        "threshold":       threshold,
        "description":     description,
        "projected_grade": projected_grade,
        "created_at":      datetime.now().isoformat(timespec="seconds"),
        "triggered":       False,
        "triggered_at":    None,
        "active":          True,
    }
    data["alerts"].append(alert)
    _save_raw(data)
    return data["alerts"]


def remove_alert(alert_id: str) -> list[dict]:
    data = _load_raw()
    data["alerts"] = [a for a in data["alerts"] if a.get("id") != alert_id]
    _save_raw(data)
    return data["alerts"]


def reset_alert(alert_id: str) -> list[dict]:
    """Re-arm a triggered alert so it can fire again."""
    data = _load_raw()
    for a in data["alerts"]:
        if a.get("id") == alert_id:
            a["triggered"]    = False
            a["triggered_at"] = None
    _save_raw(data)
    return data["alerts"]


def check_alerts(quotes: dict[str, dict]) -> list[dict]:
    """
    Evaluate all active, untriggered alerts against current quotes.
    Marks triggered alerts in the file and returns them (with quote data attached).
    """
    data = _load_raw()
    triggered = []

    for alert in data["alerts"]:
        if not alert.get("active") or alert.get("triggered"):
            continue

        ticker  = alert["ticker"]
        q       = quotes.get(ticker, {})
        if not q:
            continue

        price   = q.get("price")
        day_chg = q.get("day_change_pct")
        rel_vol = q.get("rel_volume")
        cond    = alert["condition"]
        thresh  = float(alert["threshold"])
        hit     = False

        if   cond == "price_below"   and price   is not None and price   <  thresh:
            hit = True
        elif cond == "price_above"   and price   is not None and price   >  thresh:
            hit = True
        elif cond == "day_chg_above" and day_chg is not None and day_chg >  thresh:
            hit = True
        elif cond == "day_chg_below" and day_chg is not None and day_chg < -thresh:
            hit = True
        elif cond == "rel_vol_above" and rel_vol is not None and rel_vol >  thresh:
            hit = True

        if hit:
            alert["triggered"]    = True
            alert["triggered_at"] = datetime.now().isoformat(timespec="seconds")
            triggered.append({**alert, "quote": q})

    _save_raw(data)
    return triggered
