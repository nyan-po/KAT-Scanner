"""
Rules-based scenario generator for KAT watchlist tickers.
Uses existing fetched data (EMAs, price, volume, 52W levels) to
suggest concrete conditional setups with projected grades and reasoning.
"""

GRADES = ["D", "C", "B-", "B", "B+", "A-", "A", "A+"]


def _grade_shift(grade: str, n: int) -> str:
    idx = GRADES.index(grade) if grade in GRADES else GRADES.index("C")
    return GRADES[max(0, min(len(GRADES) - 1, idx + n))]


def _nearest_round(price: float, step: float = 5.0) -> float:
    import math
    return math.floor(price / step) * step


def generate_scenarios(data: dict) -> list[dict]:
    """
    Return a list of scenario dicts, each with:
      condition, threshold, description, projected_grade,
      reasoning, level_name, priority ('high'|'medium'|'low')
    Sorted by priority then relevance.
    """
    price   = data.get("price") or 0
    ema9    = data.get("ema9")
    ema20   = data.get("ema20")
    sma50   = data.get("sma50")
    sma200  = data.get("sma200")
    w52h    = data.get("week52_high")
    w52l    = data.get("week52_low")
    day_chg = data.get("day_change_pct") or 0
    rel_vol = data.get("rel_volume")
    grade   = data.get("kat_grade") or "C"
    score   = data.get("kat_score") or 0
    signal  = (data.get("technical_signal") or "").lower()
    is_ext  = data.get("is_extended", False)

    scenarios = []

    # ── 1. EMA 9 dip + reclaim ─────────────────────────────────────────────────
    if ema9 and price > ema9 * 1.005:
        gap_pct = (price - ema9) / ema9 * 100
        if gap_pct < 15:  # only relevant if not too far extended
            proj = _grade_shift(grade, 1 if "bullish" in signal else 0)
            scenarios.append({
                "level_name":      "EMA 9 dip + reclaim",
                "condition":       "price_below",
                "threshold":       round(ema9 * 0.995, 2),  # trigger just below EMA9
                "description":     f"Dip to EMA9 (${ema9:.2f}) — momentum reset entry",
                "projected_grade": proj,
                "reasoning": (
                    f"EMA9 at ${ema9:.2f} is first dynamic support ({gap_pct:.1f}% below current). "
                    f"A dip here followed by a volume reclaim is a textbook short-term entry. "
                    f"{'Already in bullish structure — adds conviction.' if 'bullish' in signal else 'Watch for volume confirmation on reclaim.'}"
                ),
                "priority": "high",
            })

    # ── 2. EMA 20 support ──────────────────────────────────────────────────────
    if ema20 and price > ema20 * 1.01:
        gap_pct = (price - ema20) / ema20 * 100
        proj = _grade_shift(grade, 1)
        scenarios.append({
            "level_name":      "EMA 20 support test",
            "condition":       "price_below",
            "threshold":       round(ema20 * 0.998, 2),
            "description":     f"Pullback to EMA20 (${ema20:.2f}) — deeper reset, stronger base",
            "projected_grade": proj,
            "reasoning": (
                f"EMA20 at ${ema20:.2f} ({gap_pct:.1f}% below) is stronger confluence support. "
                f"Institutions often scale in at EMA20 tests. "
                f"A hold here with vol > 1.3x would signal demand absorption."
            ),
            "priority": "medium",
        })

    # ── 3. SMA 50 major support ────────────────────────────────────────────────
    if sma50 and price > sma50 * 1.02:
        gap_pct = (price - sma50) / sma50 * 100
        proj = _grade_shift(grade, 2 if score < 65 else 1)
        scenarios.append({
            "level_name":      "50 SMA institutional support",
            "condition":       "price_below",
            "threshold":       round(sma50 * 0.998, 2),
            "description":     f"Pullback to 50 SMA (${sma50:.2f}) — high R:R swing entry",
            "projected_grade": proj,
            "reasoning": (
                f"50 SMA at ${sma50:.2f} ({gap_pct:.1f}% below) is where most institutional algos "
                f"trigger buy programs. A clean test with declining volume on the drop and a "
                f"surge on reclaim = high-confidence swing setup."
            ),
            "priority": "medium",
        })

    # ── 4. 52-week high breakout ───────────────────────────────────────────────
    if w52h and price >= w52h * 0.93 and price < w52h * 1.005:
        dist_pct = (w52h - price) / price * 100
        proj = _grade_shift(grade, 2)
        scenarios.append({
            "level_name":      "52W high breakout",
            "condition":       "price_above",
            "threshold":       round(w52h * 1.002, 2),
            "description":     f"Breaks 52W high (${w52h:.2f}) — no overhead resistance",
            "projected_grade": proj,
            "reasoning": (
                f"Price is {dist_pct:.1f}% from the 52-week high of ${w52h:.2f}. "
                f"A confirmed close above 52W high on volume removes all overhead supply — "
                f"historically strong continuation signal. "
                f"Options market often goes vertical above this level."
            ),
            "priority": "high",
        })

    # ── 5. SMA 200 long-term reclaim ──────────────────────────────────────────
    if sma200 and price > sma200 * 0.97 and price < sma200 * 1.03:
        proj = _grade_shift(grade, 2)
        scenarios.append({
            "level_name":      "200 SMA reclaim",
            "condition":       "price_above",
            "threshold":       round(sma200 * 1.001, 2),
            "description":     f"Reclaims 200 SMA (${sma200:.2f}) — long-term trend flip",
            "projected_grade": proj,
            "reasoning": (
                f"Price is near the 200 SMA (${sma200:.2f}), the dividing line between "
                f"bull and bear market structure. A reclaim with vol is a major structural "
                f"shift and will attract long-only funds."
            ),
            "priority": "high",
        })

    # ── 6. Round number psychological level ───────────────────────────────────
    _rnd5 = _nearest_round(price, 5.0)
    if _rnd5 > 0 and (_rnd5 / price) >= 0.91 and _rnd5 < price:
        proj = grade  # round numbers maintain grade, confirmation-dependent
        scenarios.append({
            "level_name":      f"${_rnd5:.0f} psychological support",
            "condition":       "price_below",
            "threshold":       float(_rnd5),
            "description":     f"${_rnd5:.0f} round-number support — options pin / stop cluster",
            "projected_grade": proj,
            "reasoning": (
                f"${_rnd5:.0f} is a psychological magnet — retail stops and options strikes "
                f"cluster here. A dip to ${_rnd5:.0f} that holds = short squeeze fuel. "
                f"Watch time-of-sale for absorption (large bids holding the level)."
            ),
            "priority": "low",
        })

    # ── 7. Volume confirmation (currently quiet) ───────────────────────────────
    _cur_rv = rel_vol or 0
    if _cur_rv < 1.3:
        vol_thresh = 1.5 if _cur_rv < 0.8 else 2.0
        proj = _grade_shift(grade, 1)
        scenarios.append({
            "level_name":      "Volume surge confirmation",
            "condition":       "rel_vol_above",
            "threshold":       vol_thresh,
            "description":     f"Rel volume exceeds {vol_thresh}x — validates any directional move",
            "projected_grade": proj,
            "reasoning": (
                f"Current rel volume is only {_cur_rv:.1f}x — the stock is quiet. "
                f"A {vol_thresh}x+ surge usually precedes or accompanies a significant move. "
                f"Combine with price action at a key level for best results."
            ),
            "priority": "medium",
        })

    # ── 8. Momentum continuation (already moving) ─────────────────────────────
    if day_chg >= 3:
        next_thresh = round(day_chg + 2, 1)
        proj = _grade_shift(grade, 1)
        scenarios.append({
            "level_name":      "Momentum continuation",
            "condition":       "day_chg_above",
            "threshold":       next_thresh,
            "description":     f"Day gain exceeds +{next_thresh}% — extended momentum",
            "projected_grade": proj,
            "reasoning": (
                f"Already up {day_chg:.1f}% today. A push to +{next_thresh}% signals "
                f"strong institutional buying or a catalyst-driven trend day. "
                f"{'Caution: extended above EMA9 — size down.' if is_ext else 'Healthy structure supports continuation.'}"
            ),
            "priority": "medium",
        })

    # ── 9. Selloff / stop-loss alert ──────────────────────────────────────────
    stop_thresh = 4.0 if grade in ("A+", "A", "A-", "B+") else 5.0
    proj_down   = _grade_shift(grade, -1)
    scenarios.append({
        "level_name":      "Selloff / exit alert",
        "condition":       "day_chg_below",
        "threshold":       stop_thresh,
        "description":     f"Day loss exceeds -{stop_thresh}% — risk management trigger",
        "projected_grade": proj_down,
        "reasoning": (
            f"A -{stop_thresh}%+ day on rising volume breaks short-term structure. "
            f"This alert helps you manage risk automatically — get the Discord ping "
            f"before it becomes a bigger problem."
        ),
        "priority": "high",
    })

    # Sort: high priority first, then by condition type
    _order = {"high": 0, "medium": 1, "low": 2}
    scenarios.sort(key=lambda s: _order.get(s["priority"], 1))

    return scenarios
