"""
Filter logic for the screener. Applies configured filters to the scored result set.
"""
import logging
from datetime import date, datetime
from .grading import grade_passes_minimum

logger = logging.getLogger(__name__)

ETF_QUOTE_TYPES = {"ETF", "MUTUALFUND", "INDEX", "FUTURE"}


def _safe_float(val) -> float | None:
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def apply_filters(results: list[dict], filters: dict) -> list[dict]:
    """
    Apply filter criteria to a list of scored ticker dicts.
    Returns the filtered list.
    """
    passed = []
    for r in results:
        if _passes_all(r, filters):
            passed.append(r)
    return passed


def _passes_all(r: dict, f: dict) -> bool:
    price = _safe_float(r.get("price"))
    mktcap = _safe_float(r.get("market_cap"))
    avg_vol = _safe_float(r.get("avg_volume"))
    rel_vol = _safe_float(r.get("rel_volume"))
    rev_growth = _safe_float(r.get("revenue_growth"))
    pe = _safe_float(r.get("pe"))
    grade = r.get("kat_grade", "D")
    quote_type = (r.get("quote_type") or "").upper()
    earnings_date = r.get("earnings_date")

    # Price filters
    min_price = _safe_float(f.get("min_price"))
    max_price = _safe_float(f.get("max_price"))
    if min_price is not None and price is not None and price < min_price:
        return False
    if max_price is not None and price is not None and price > max_price:
        return False

    # Market cap
    min_mktcap = _safe_float(f.get("min_market_cap"))
    if min_mktcap is not None and mktcap is not None and mktcap < min_mktcap:
        return False

    # Average volume
    min_avg_vol = _safe_float(f.get("min_avg_volume"))
    if min_avg_vol is not None and avg_vol is not None and avg_vol < min_avg_vol:
        return False

    # Relative volume
    min_rel_vol = _safe_float(f.get("min_relative_volume"))
    if min_rel_vol is not None and rel_vol is not None and rel_vol < min_rel_vol:
        return False

    # Revenue growth
    min_rev_growth = _safe_float(f.get("min_revenue_growth"))
    if min_rev_growth is not None and rev_growth is not None and rev_growth < min_rev_growth:
        return False
    if f.get("only_positive_revenue_growth") and rev_growth is not None and rev_growth <= 0:
        return False

    # PE cap
    max_pe = _safe_float(f.get("max_pe"))
    if max_pe is not None and pe is not None and pe > 0 and pe > max_pe:
        return False

    # KAT grade minimum
    min_grade = f.get("min_grade")
    if min_grade:
        if not grade_passes_minimum(grade, min_grade):
            return False

    # ETF exclusion
    if f.get("exclude_etfs") and quote_type in ETF_QUOTE_TYPES:
        return False

    # Low-priced stock exclusion (< $5)
    if f.get("exclude_low_priced") and price is not None and price < 5.0:
        return False

    # Earnings within X days filter
    earnings_within = f.get("earnings_within_days")
    if earnings_within is not None and earnings_date:
        try:
            ed = datetime.strptime(str(earnings_date), "%Y-%m-%d").date()
            days_away = (ed - date.today()).days
            if not (0 <= days_away <= int(earnings_within)):
                return False
        except Exception:
            pass

    return True


def sort_results(results: list[dict], key: str = "kat_score", ascending: bool = False) -> list[dict]:
    return sorted(results, key=lambda r: r.get(key, 0), reverse=not ascending)


def limit_results(results: list[dict], max_results: int | None) -> list[dict]:
    if max_results and len(results) > max_results:
        return results[:max_results]
    return results
