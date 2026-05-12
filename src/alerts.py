"""
Alert management for KAT Market Screener.
Alerts are stored as plain dicts and managed through session state in the UI.
"""
import uuid
from datetime import datetime

from .grading import GRADE_ORDER

CONDITION_LABELS = {
    "score_gte":       "KAT Score ≥",
    "grade_gte":       "KAT Grade ≥",
    "rel_volume_gte":  "Rel Volume ≥",
    "day_change_gte":  "Day Change % ≥",
    "day_change_lte":  "Day Change % ≤",
    "price_gte":       "Price ≥ $",
    "price_lte":       "Price ≤ $",
}


def add_alert(ticker: str, condition: str, threshold) -> dict:
    """Create and return a new alert dict (not yet stored anywhere)."""
    return {
        "id": str(uuid.uuid4())[:8],
        "ticker": ticker.upper().strip(),
        "condition": condition,
        "threshold": threshold,
        "triggered": False,
        "created_at": datetime.now().isoformat(),
        "last_triggered": None,
    }


def remove_alert(alerts: list[dict], alert_id: str) -> list[dict]:
    """Return a new list with the given alert removed."""
    return [a for a in alerts if a["id"] != alert_id]


def reset_alert(alerts: list[dict], alert_id: str) -> list[dict]:
    """Clear the triggered state on an alert in-place; returns the same list."""
    for a in alerts:
        if a["id"] == alert_id:
            a["triggered"] = False
            a["last_triggered"] = None
    return alerts


def check_alerts(alerts: list[dict], results: list[dict]) -> list[dict]:
    """
    Evaluate each alert against the latest scan results.
    Returns a list of triggered alert dicts (with the matching result attached).
    Mutates the triggered/last_triggered fields of matched alerts.
    """
    by_ticker = {r.get("ticker", "").upper(): r for r in results}
    triggered = []
    for alert in alerts:
        result = by_ticker.get(alert["ticker"])
        if result is None:
            continue
        if _condition_met(alert, result):
            alert["triggered"] = True
            alert["last_triggered"] = datetime.now().isoformat()
            triggered.append({**alert, "result": result})
    return triggered


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _condition_met(alert: dict, result: dict) -> bool:
    condition = alert["condition"]
    threshold = alert["threshold"]

    if condition == "score_gte":
        return (result.get("kat_score") or 0) >= float(threshold)

    if condition == "grade_gte":
        grade = result.get("kat_grade", "D")
        if threshold not in GRADE_ORDER or grade not in GRADE_ORDER:
            return False
        # Lower index in GRADE_ORDER = better grade
        return GRADE_ORDER.index(grade) <= GRADE_ORDER.index(threshold)

    if condition == "rel_volume_gte":
        return (result.get("rel_volume") or 0) >= float(threshold)

    if condition == "day_change_gte":
        return (result.get("day_change_pct") or 0) >= float(threshold)

    if condition == "day_change_lte":
        return (result.get("day_change_pct") or 0) <= float(threshold)

    if condition == "price_gte":
        return (result.get("price") or 0) >= float(threshold)

    if condition == "price_lte":
        val = result.get("price")
        return val is not None and float(val) <= float(threshold)

    return False
