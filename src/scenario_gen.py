"""
Rules-based scenario generator for KAT watchlist tickers.

Projected grades are computed by re-running only the affected scoring
components under the scenario's hypothetical conditions, using the
already-stored component scores from the original KAT analysis.
"""
import math
from .scoring import _volume_score, _technical_score
from .grading import score_to_grade

ST_CEILING = 68
LT_CEILING = 72

CONDITION_LABELS = {   # kept here for reference; canonical copy is in alerts.py
    "price_below":    "Price drops below $",
    "price_above":    "Price breaks above $",
    "day_chg_above":  "Day change exceeds +%",
    "day_chg_below":  "Day change drops below -%",
    "rel_vol_above":  "Rel volume exceeds x",
}


def _simulate_score(data: dict, scenario: dict) -> tuple[int, str]:
    """
    Re-score the ticker with only the components that the scenario changes.
    Keeps every other component at its current value.
    Returns (projected_kat_score, projected_grade).
    """
    cond   = scenario["condition"]
    thresh = float(scenario["threshold"])
    mode   = data.get("mode", "short_term")

    if mode == "long_term":
        # Scenarios mostly affect technical/market dynamics, minor in LT model.
        # Apply a modest fixed adjustment based on scenario bullishness.
        delta = {
            "price_above":    8,
            "price_below":    4,   # support hold = constructive
            "rel_vol_above":  5,
            "day_chg_above":  6,
            "day_chg_below": -8,
        }.get(cond, 0)
        raw_score = max(0, min(100, (data.get("kat_score") or 50) + delta))
        return raw_score, score_to_grade(raw_score)

    # ── Short-term: reconstruct from stored component scores ──────────────────
    cat_score   = data.get("score_catalyst", 5)
    vol_score   = data.get("score_volume", 8)
    tech_score  = data.get("score_technical", 10)
    earn_score  = data.get("score_earnings", 7)
    sect_score  = data.get("score_sector", 5)
    short_score = data.get("score_short_interest", 2)
    risk_pen    = data.get("score_risk_penalty", 0)
    options     = 3   # constant placeholder in scorer
    avg_vol     = data.get("avg_volume")
    cur_rv      = data.get("rel_volume") or 0

    if cond == "price_below":
        # Price dips to support level and reclaims — implies bullish reclaim with vol
        hyp_rv     = max(cur_rv, 1.3)
        vol_score  = _volume_score(hyp_rv, avg_vol)
        tech_score = max(tech_score, 16)   # at least "bullish"

    elif cond == "price_above":
        # Price breaks above resistance — typically high vol breakout
        hyp_rv     = max(cur_rv, 2.0)
        vol_score  = _volume_score(hyp_rv, avg_vol)
        tech_score = 20   # "bullish with volume"

    elif cond == "rel_vol_above":
        # Pure volume surge; also nudges technical (action attracts momentum traders)
        vol_score  = _volume_score(thresh, avg_vol)
        tech_score = max(tech_score, 14)

    elif cond == "day_chg_above":
        # Momentum continuation — strong up day with elevated vol
        hyp_rv     = max(cur_rv, 1.5)
        vol_score  = _volume_score(hyp_rv, avg_vol)
        tech_score = max(tech_score, 16)   # bullish

    elif cond == "day_chg_below":
        # Selloff alert — bearish pressure, selling volume
        hyp_rv     = max(cur_rv, 1.5)
        vol_score  = _volume_score(hyp_rv, avg_vol)
        tech_score = 4    # bearish signal

    raw   = cat_score + vol_score + tech_score + earn_score + sect_score + short_score + options - risk_pen
    total = max(0, min(100, round(raw / ST_CEILING * 100)))
    return total, score_to_grade(total)


def _nearest_round(price: float, step: float = 5.0) -> float:
    return math.floor(price / step) * step


def generate_scenarios(data: dict) -> list[dict]:
    """
    Generate conditional setups from existing ticker data.
    Each scenario has:
      condition, threshold, description, projected_grade, projected_score,
      reasoning, level_name, priority, score_delta
    Sorted by priority then score_delta descending.
    """
    price   = data.get("price") or 0
    ema9    = data.get("ema9")
    ema20   = data.get("ema20")
    sma50   = data.get("sma50")
    sma200  = data.get("sma200")
    w52h    = data.get("week52_high")
    day_chg = data.get("day_change_pct") or 0
    rel_vol = data.get("rel_volume") or 0
    score   = data.get("kat_score") or 0
    signal  = (data.get("technical_signal") or "").lower()
    is_ext  = data.get("is_extended", False)

    scenarios = []

    def _make(level_name, condition, threshold, description, reasoning, priority):
        sc = {
            "level_name":  level_name,
            "condition":   condition,
            "threshold":   threshold,
            "description": description,
            "reasoning":   reasoning,
            "priority":    priority,
        }
        proj_score, proj_grade = _simulate_score(data, sc)
        sc["projected_score"] = proj_score
        sc["projected_grade"] = proj_grade
        sc["score_delta"]     = proj_score - score
        return sc

    # ── 1. EMA 9 dip + reclaim ─────────────────────────────────────────────────
    if ema9 and price > ema9 * 1.005:
        gap_pct = (price - ema9) / ema9 * 100
        if gap_pct < 15:
            scenarios.append(_make(
                level_name  = "EMA 9 dip + reclaim",
                condition   = "price_below",
                threshold   = round(ema9 * 0.995, 2),
                description = f"Dip to EMA9 (${ema9:.2f}) — momentum reset entry",
                reasoning   = (
                    f"EMA9 at ${ema9:.2f} is first dynamic support ({gap_pct:.1f}% below). "
                    f"A dip here + volume reclaim = textbook short-term entry. "
                    f"{'Already in bullish structure — adds conviction.' if 'bullish' in signal else 'Watch for vol confirmation on reclaim.'}"
                ),
                priority    = "high",
            ))

    # ── 2. EMA 20 support ──────────────────────────────────────────────────────
    if ema20 and price > ema20 * 1.01:
        gap_pct = (price - ema20) / ema20 * 100
        scenarios.append(_make(
            level_name  = "EMA 20 support test",
            condition   = "price_below",
            threshold   = round(ema20 * 0.998, 2),
            description = f"Pullback to EMA20 (${ema20:.2f}) — deeper reset, stronger base",
            reasoning   = (
                f"EMA20 at ${ema20:.2f} ({gap_pct:.1f}% below) is stronger confluence support. "
                f"Institutions often scale in at EMA20 tests. "
                f"Hold + vol > 1.3x signals demand absorption."
            ),
            priority    = "medium",
        ))

    # ── 3. SMA 50 major support ────────────────────────────────────────────────
    if sma50 and price > sma50 * 1.02:
        gap_pct = (price - sma50) / sma50 * 100
        scenarios.append(_make(
            level_name  = "50 SMA institutional support",
            condition   = "price_below",
            threshold   = round(sma50 * 0.998, 2),
            description = f"Pullback to 50 SMA (${sma50:.2f}) — high R:R swing entry",
            reasoning   = (
                f"50 SMA at ${sma50:.2f} ({gap_pct:.1f}% below) triggers institutional buy algos. "
                f"Clean test + declining vol on drop + surge on reclaim = high-confidence swing setup."
            ),
            priority    = "medium",
        ))

    # ── 4. 52-week high breakout ───────────────────────────────────────────────
    if w52h and price >= w52h * 0.93 and price < w52h * 1.005:
        dist_pct = (w52h - price) / price * 100
        scenarios.append(_make(
            level_name  = "52W high breakout",
            condition   = "price_above",
            threshold   = round(w52h * 1.002, 2),
            description = f"Breaks 52W high (${w52h:.2f}) — no overhead resistance",
            reasoning   = (
                f"Price is {dist_pct:.1f}% from 52W high of ${w52h:.2f}. "
                f"A confirmed close above on volume removes all overhead supply. "
                f"Options market often goes vertical above this level."
            ),
            priority    = "high",
        ))

    # ── 5. SMA 200 reclaim ────────────────────────────────────────────────────
    if sma200 and price > sma200 * 0.97 and price < sma200 * 1.03:
        scenarios.append(_make(
            level_name  = "200 SMA reclaim",
            condition   = "price_above",
            threshold   = round(sma200 * 1.001, 2),
            description = f"Reclaims 200 SMA (${sma200:.2f}) — long-term trend flip",
            reasoning   = (
                f"200 SMA at ${sma200:.2f} divides bull/bear structure. "
                f"Reclaim with vol is a major structural shift that attracts long-only funds."
            ),
            priority    = "high",
        ))

    # ── 6. Round number psychological level ───────────────────────────────────
    _rnd = _nearest_round(price, 5.0)
    if _rnd > 0 and (_rnd / price) >= 0.91 and _rnd < price:
        scenarios.append(_make(
            level_name  = f"${_rnd:.0f} psychological support",
            condition   = "price_below",
            threshold   = float(_rnd),
            description = f"${_rnd:.0f} round-number support — options pin / stop cluster",
            reasoning   = (
                f"${_rnd:.0f} attracts retail stops and options strikes. "
                f"A dip that holds here = short squeeze fuel. "
                f"Watch time-of-sale for absorption at the level."
            ),
            priority    = "low",
        ))

    # ── 7. Volume confirmation (currently quiet) ───────────────────────────────
    if rel_vol < 1.3:
        vol_thresh = 1.5 if rel_vol < 0.8 else 2.0
        scenarios.append(_make(
            level_name  = "Volume surge confirmation",
            condition   = "rel_vol_above",
            threshold   = vol_thresh,
            description = f"Rel volume exceeds {vol_thresh}x — validates directional move",
            reasoning   = (
                f"Current rel vol is only {rel_vol:.1f}x — stock is quiet. "
                f"A {vol_thresh}x+ surge usually precedes or accompanies a significant move. "
                f"Combine with price action at a key level."
            ),
            priority    = "medium",
        ))

    # ── 8. Momentum continuation (already moving) ─────────────────────────────
    if day_chg >= 3:
        next_thresh = round(day_chg + 2, 1)
        scenarios.append(_make(
            level_name  = "Momentum continuation",
            condition   = "day_chg_above",
            threshold   = next_thresh,
            description = f"Day gain exceeds +{next_thresh}% — extended trend day",
            reasoning   = (
                f"Already up {day_chg:.1f}% today. A push to +{next_thresh}% signals "
                f"institutional buying or a catalyst-driven trend day. "
                f"{'Caution: extended above EMA9 — size down.' if is_ext else 'Healthy structure supports continuation.'}"
            ),
            priority    = "medium",
        ))

    # ── 9. Selloff / stop-loss alert ──────────────────────────────────────────
    stop_thresh = 4.0 if score >= 75 else 5.0
    scenarios.append(_make(
        level_name  = "Selloff / exit alert",
        condition   = "day_chg_below",
        threshold   = stop_thresh,
        description = f"Day loss exceeds -{stop_thresh}% — risk management trigger",
        reasoning   = (
            f"A -{stop_thresh}%+ day on rising volume breaks short-term structure. "
            f"This alert lets you manage risk automatically via Discord ping."
        ),
        priority    = "high",
    ))

    # Sort: high priority first, then largest positive score_delta first
    _order = {"high": 0, "medium": 1, "low": 2}
    scenarios.sort(key=lambda s: (_order.get(s["priority"], 1), -s["score_delta"]))

    return scenarios
