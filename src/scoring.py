"""
KAT scoring engine. Produces a 0-100 score for short_term and long_term modes.
"""
import logging
from .technicals import calculate_technicals
from .fundamentals import analyze_fundamentals
from .news import analyze_news, score_earnings_timing

logger = logging.getLogger(__name__)

# Sector tailwind tiers for scoring
HIGH_TAILWIND_SECTORS = {
    "Technology", "Semiconductors", "AI Infrastructure", "Cybersecurity",
    "Software", "Nuclear and Power",
}
MEDIUM_TAILWIND_SECTORS = {
    "Healthcare", "Defense", "Industrials", "Financials", "Consumer Discretionary",
    "Communication Services",
}
LOW_TAILWIND_SECTORS = {
    "Energy", "Utilities", "Real Estate", "Consumer Staples", "Materials",
}

# KAT custom sector tags take precedence
HIGH_TAILWIND_KAT = {
    "AI Infrastructure", "Semiconductors", "Cybersecurity", "Software",
    "Nuclear and Power", "Defense",
}


def _sector_tailwind_score(sector: str, industry: str, kat_sector: str | None) -> int:
    check = kat_sector or sector
    if any(h in check for h in HIGH_TAILWIND_KAT | HIGH_TAILWIND_SECTORS):
        return 10
    if any(m in check for m in MEDIUM_TAILWIND_SECTORS):
        return 6
    return 3


def _volume_score(rel_volume: float | None, avg_volume: float | None) -> int:
    """Score relative volume contribution (max 20)."""
    if rel_volume is None:
        return 8  # unknown — give benefit of the doubt

    if rel_volume >= 5.0:
        score = 20
    elif rel_volume >= 3.0:
        score = 18
    elif rel_volume >= 2.0:
        score = 15
    elif rel_volume >= 1.5:
        score = 13
    elif rel_volume >= 1.2:
        score = 11
    elif rel_volume >= 0.8:
        score = 8
    elif rel_volume >= 0.5:
        score = 5
    else:
        score = 2

    # Penalize thinly traded even if rel_volume is high
    if avg_volume and avg_volume < 100000:
        score = max(0, score - 5)

    return score


def _short_interest_score(short_pct: float | None) -> int:
    """Max 5 points for short squeeze potential."""
    if short_pct is None:
        return 2
    if short_pct >= 25:
        return 5
    elif short_pct >= 15:
        return 4
    elif short_pct >= 8:
        return 3
    return 1


def _technical_score(tech: dict) -> int:
    """Convert technical signal to score (max 20)."""
    signal = tech.get("tech_signal", "")
    if signal == "bullish with volume":
        return 20
    elif signal == "bullish":
        return 16
    elif signal == "bullish but extended":
        return 11  # good underlying trend but risky entry
    elif signal == "reversal watch":
        return 12
    elif signal == "neutral":
        return 10
    elif signal == "bearish":
        return 4
    return 8  # insufficient data — don't punish hard


def _risk_penalty(data: dict, tech: dict, fund: dict) -> int:
    """Compute risk penalty (reduces from 5 max bonus; penalty is subtracted)."""
    penalty = 0

    # Low liquidity
    avg_vol = data.get("avg_volume")
    if avg_vol and avg_vol < 200000:
        penalty += 3
    elif avg_vol and avg_vol < 500000:
        penalty += 1

    # Micro-cap
    mktcap = data.get("market_cap")
    if mktcap and mktcap < 50_000_000:
        penalty += 4
    elif mktcap and mktcap < 200_000_000:
        penalty += 2

    # Negative revenue growth
    rev_growth = data.get("revenue_growth")
    if rev_growth is not None and rev_growth < -10:
        penalty += 3

    # Very high debt
    dtc = data.get("debt_to_cash")
    if dtc and dtc > 10:
        penalty += 4
    elif dtc and dtc > 5:
        penalty += 2

    # Already extremely extended
    if tech.get("is_extended") and data.get("day_change_pct") and data["day_change_pct"] > 20:
        penalty += 3

    # Dilution signal from news
    if data.get("dilution_flag"):
        penalty += 5

    # Missing data
    missing = fund.get("missing_fundamental_fields", 0)
    if missing >= 5:
        penalty += 3
    elif missing >= 3:
        penalty += 1

    return min(penalty, 20)


def score_short_term(data: dict, kat_sector: str | None = None) -> dict:
    """
    Score a ticker for short-term potential.
    Returns score dict including component scores and total.
    """
    tech = calculate_technicals(data.get("price_history"), data.get("price"))
    fund = analyze_fundamentals(data)
    news = analyze_news(data.get("news_headlines", []), data.get("earnings_date"))

    # Attach news analysis results back to data for output
    data["dilution_flag"] = news.get("dilution_flag", False)

    catalyst_score = news.get("catalyst_score", 5)  # max 20
    vol_score = _volume_score(data.get("rel_volume"), data.get("avg_volume"))  # max 20
    tech_score = _technical_score(tech)  # max 20
    earnings_score = score_earnings_timing(data.get("earnings_date"))  # max 15
    sector_score = _sector_tailwind_score(
        data.get("sector", ""), data.get("industry", ""), kat_sector
    )  # max 10
    short_score = _short_interest_score(data.get("short_percent_float"))  # max 5
    options_score = 3  # placeholder, always moderate
    risk_pen = _risk_penalty(data, tech, fund)

    raw = (
        catalyst_score
        + vol_score
        + tech_score
        + earnings_score
        + sector_score
        + short_score
        + options_score
        - risk_pen
    )

    # Normalize to 0-100.
    # Use a realistic "excellent setup" ceiling (~68) rather than the theoretical
    # max (95), so good-but-not-perfect setups land in the B/A range instead of
    # all compressing into D.
    ceiling = 68
    total = max(0, min(100, round(raw / ceiling * 100)))

    volume_signal = _build_volume_signal(data)
    setup_type = _short_term_setup_type(data, tech, news)
    action, invalidation = _suggested_action_short(total, tech, data)
    confidence = _confidence_level(data, tech, fund, news)
    strongest_reason, biggest_risk = _reasons_short(data, tech, news, fund)

    return {
        "kat_score": total,
        "mode": "short_term",
        "setup_type": setup_type,
        "suggested_action": action,
        "invalidation": invalidation,
        "confidence": confidence,
        "strongest_reason": strongest_reason,
        "biggest_risk": biggest_risk,
        "catalyst_summary": news.get("catalyst_summary", "No recent news found"),
        "catalyst_quality": news.get("catalyst_quality", "none"),
        "volume_signal": volume_signal,
        "valuation_signal": fund.get("valuation_signal", "unknown"),
        "technical_signal": tech.get("tech_signal", "insufficient data"),
        "technical_notes": tech.get("tech_notes", ""),
        "fundamental_signal": fund.get("fundamental_signal", "neutral"),
        "fundamental_notes": fund.get("fundamental_notes", ""),
        # component breakdown
        "score_catalyst": catalyst_score,
        "score_volume": vol_score,
        "score_technical": tech_score,
        "score_earnings": earnings_score,
        "score_sector": sector_score,
        "score_short_interest": short_score,
        "score_risk_penalty": risk_pen,
        # technicals
        "ema9": tech.get("ema9"),
        "ema20": tech.get("ema20"),
        "sma50": tech.get("sma50"),
        "sma200": tech.get("sma200"),
        "return_5d": tech.get("return_5d"),
        "return_20d": tech.get("return_20d"),
        "is_extended": tech.get("is_extended"),
    }


def score_long_term(data: dict, kat_sector: str | None = None) -> dict:
    """
    Score a ticker for long-term potential.
    Returns score dict including component scores and total.
    """
    tech = calculate_technicals(data.get("price_history"), data.get("price"))
    fund = analyze_fundamentals(data)
    news = analyze_news(data.get("news_headlines", []), data.get("earnings_date"))

    data["dilution_flag"] = news.get("dilution_flag", False)

    # Long-term weights: fundamentals dominate
    revenue_growth = data.get("revenue_growth")
    rev_score = 0
    if revenue_growth is not None:
        if revenue_growth > 40:
            rev_score = 20
        elif revenue_growth > 25:
            rev_score = 17
        elif revenue_growth > 15:
            rev_score = 13
        elif revenue_growth > 5:
            rev_score = 9
        elif revenue_growth > 0:
            rev_score = 5
        else:
            rev_score = 0
    else:
        rev_score = 5  # unknown — small baseline

    # Earnings trend (max 15)
    earnings_score_lt = 7  # baseline
    eg = data.get("earnings_growth")
    if eg is not None:
        if eg > 30:
            earnings_score_lt = 15
        elif eg > 15:
            earnings_score_lt = 12
        elif eg > 0:
            earnings_score_lt = 9
        elif eg < -20:
            earnings_score_lt = 2
        else:
            earnings_score_lt = 5
    op_margin = data.get("operating_margin")
    if op_margin is not None:
        if op_margin > 20:
            earnings_score_lt = min(15, earnings_score_lt + 3)
        elif op_margin < -20:
            earnings_score_lt = max(0, earnings_score_lt - 4)

    # Balance sheet (max 15)
    bs_score = 0
    dtc = data.get("debt_to_cash")
    fcf = data.get("free_cash_flow")
    if dtc is not None:
        if dtc < 0.3:
            bs_score = 15
        elif dtc < 1.0:
            bs_score = 12
        elif dtc < 2.0:
            bs_score = 8
        elif dtc < 5.0:
            bs_score = 3
        else:
            bs_score = 0
    else:
        bs_score = 6

    # FCF trend (max 15)
    fcf_score = 7
    if fcf is not None:
        mktcap = data.get("market_cap") or 1
        fcf_yield = fcf / mktcap * 100
        if fcf > 0 and fcf_yield > 5:
            fcf_score = 15
        elif fcf > 0 and fcf_yield > 2:
            fcf_score = 12
        elif fcf > 0:
            fcf_score = 9
        elif fcf < 0:
            # Acceptable for high-growth, but penalize heavy burners
            fcf_score = 5 if revenue_growth and revenue_growth > 20 else 2

    # Valuation reasonableness (max 10)
    val_score = 5
    pe = data.get("pe")
    fpe = data.get("forward_pe")
    ps = data.get("ps_ratio")
    if pe and pe > 0:
        if pe < 20:
            val_score = 10
        elif pe < 35:
            val_score = 7
        elif pe < 60:
            val_score = 4
        else:
            val_score = 1
    elif fpe and fpe > 0:
        if fpe < 25:
            val_score = 8
        elif fpe < 50:
            val_score = 5
        else:
            val_score = 2
    elif ps:
        if ps < 10:
            val_score = 7
        elif ps < 25:
            val_score = 4
        else:
            val_score = 2

    # Sector tailwind (max 10)
    sector_score = _sector_tailwind_score(
        data.get("sector", ""), data.get("industry", ""), kat_sector
    )

    # Execution proxy: news quality + management signals (max 10)
    exec_score = min(10, max(4, news.get("catalyst_score", 5) // 2 + 2))

    # Dilution risk penalty (max 5 — subtracted)
    dilution_pen = 5 if news.get("dilution_flag") else 0
    if data.get("short_percent_float") and data["short_percent_float"] > 30:
        dilution_pen = min(5, dilution_pen + 2)

    raw = (
        rev_score
        + earnings_score_lt
        + bs_score
        + fcf_score
        + val_score
        + sector_score
        + exec_score
        - dilution_pen
    )

    # Normalize against realistic excellent ceiling (~72), not theoretical max (95)
    ceiling = 72
    total = max(0, min(100, round(raw / ceiling * 100)))

    volume_signal = _build_volume_signal(data)
    setup_type = _long_term_setup_type(data, tech, fund)
    action, invalidation = _suggested_action_long(total, data, fund)
    confidence = _confidence_level(data, tech, fund, news)
    strongest_reason, biggest_risk = _reasons_long(data, tech, fund, news)

    return {
        "kat_score": total,
        "mode": "long_term",
        "setup_type": setup_type,
        "suggested_action": action,
        "invalidation": invalidation,
        "confidence": confidence,
        "strongest_reason": strongest_reason,
        "biggest_risk": biggest_risk,
        "catalyst_summary": news.get("catalyst_summary", "No recent news found"),
        "catalyst_quality": news.get("catalyst_quality", "none"),
        "volume_signal": volume_signal,
        "valuation_signal": fund.get("valuation_signal", "unknown"),
        "technical_signal": tech.get("tech_signal", "insufficient data"),
        "technical_notes": tech.get("tech_notes", ""),
        "fundamental_signal": fund.get("fundamental_signal", "neutral"),
        "fundamental_notes": fund.get("fundamental_notes", ""),
        # component breakdown
        "score_revenue": rev_score,
        "score_earnings_lt": earnings_score_lt,
        "score_balance_sheet": bs_score,
        "score_fcf": fcf_score,
        "score_valuation": val_score,
        "score_sector": sector_score,
        "score_execution": exec_score,
        "score_dilution_penalty": dilution_pen,
        # technicals
        "ema9": tech.get("ema9"),
        "ema20": tech.get("ema20"),
        "sma50": tech.get("sma50"),
        "sma200": tech.get("sma200"),
        "return_5d": tech.get("return_5d"),
        "return_20d": tech.get("return_20d"),
        "is_extended": tech.get("is_extended"),
    }


def _build_volume_signal(data: dict) -> str:
    rv = data.get("rel_volume")
    avg_vol = data.get("avg_volume")
    if rv is None:
        return "volume unknown"
    if avg_vol and avg_vol < 200000:
        return f"thin ({rv:.1f}x rel vol, low avg)"
    if rv >= 3.0:
        return f"unusual volume ({rv:.1f}x)"
    elif rv >= 2.0:
        return f"elevated ({rv:.1f}x)"
    elif rv >= 1.2:
        return f"above average ({rv:.1f}x)"
    elif rv >= 0.8:
        return f"normal ({rv:.1f}x)"
    return f"below average ({rv:.1f}x)"


def _short_term_setup_type(data: dict, tech: dict, news: dict) -> str:
    signal = tech.get("tech_signal", "")
    rv = data.get("rel_volume") or 0
    day_change = data.get("day_change_pct") or 0
    short_pct = data.get("short_percent_float") or 0
    earnings_date = data.get("earnings_date")
    cat_quality = news.get("catalyst_quality", "")

    avg_vol = data.get("avg_volume") or 0
    if avg_vol < 100000 and rv < 1.0:
        return "avoid/no trade"

    if earnings_date:
        return "earnings mover"

    if short_pct >= 20 and rv >= 2.0:
        return "squeeze watch"

    if day_change > 4 and rv >= 2.0 and "bullish" in signal:
        return "gap-up continuation"

    if day_change < -5 and rv >= 1.5:
        if "reversal" in signal or "above_ema9" in str(tech.get("above_ema9")):
            return "gap-down reversal"

    if rv >= 2.0 and day_change > 2 and "bullish" in signal:
        return "momentum runner"

    if "bullish" in signal and rv >= 1.2:
        return "breakout candidate"

    if "reversal" in signal:
        return "VWAP reclaim candidate"

    if "bearish" not in signal and "cat" in cat_quality:
        return "sector sympathy play"

    if "bearish" in signal:
        return "avoid/no trade"

    return "watchlist"


def _long_term_setup_type(data: dict, tech: dict, fund: dict) -> str:
    sector = data.get("sector", "")
    industry = data.get("industry", "")
    rev_growth = data.get("revenue_growth") or 0
    pe = data.get("pe")
    mktcap = data.get("market_cap") or 0
    fund_signal = fund.get("fundamental_signal", "neutral")

    if any(s in sector for s in ["Technology", "Semiconductors"]) and rev_growth > 20:
        if "AI" in industry or "Semiconductor" in industry:
            return "AI infrastructure leader" if "AI" in industry else "semiconductor leader"
        return "software compounder"

    if "Nuclear" in sector or "nuclear" in industry.lower() or "uranium" in industry.lower():
        return "nuclear/power infrastructure play"

    if "Defense" in sector or "Aerospace" in industry:
        return "defense play"

    if rev_growth > 25 and mktcap < 5_000_000_000:
        return "speculative growth"

    if rev_growth > 15 and fund_signal in ("strong", "positive"):
        return "growth compounder"

    if pe and pe > 0 and pe < 20 and fund_signal in ("strong", "positive"):
        return "value compounder"

    if fund_signal in ("weak", "poor"):
        if rev_growth > 10:
            return "turnaround candidate"
        return "avoid/no trade"

    if pe and pe > 80:
        return "overvalued/watch only"

    return "watchlist"


def _suggested_action_short(score: int, tech: dict, data: dict) -> tuple[str, str]:
    rv = data.get("rel_volume") or 0
    signal = tech.get("tech_signal", "")
    extended = tech.get("is_extended", False)

    if score >= 85 and "bullish" in signal and not extended and rv >= 1.5:
        action = "buy zone"
        inv = "Loses key support or volume dries up"
    elif score >= 80:
        action = "wait for entry"
        inv = "Break below 9 EMA or relative volume drops under 1x"
    elif score >= 75:
        action = "watchlist"
        inv = "Needs confirmation: breakout or volume surge"
    elif score >= 65:
        action = "watchlist"
        inv = "Speculative — small size only if chart confirms"
    else:
        action = "avoid"
        inv = "Insufficient setup quality"

    return action, inv


def _suggested_action_long(score: int, data: dict, fund: dict) -> tuple[str, str]:
    bs_signal = fund.get("balance_sheet_signal", "")
    dilution = data.get("dilution_flag", False)

    if score >= 85 and not dilution and "stressed" not in bs_signal:
        action = "buy zone / accumulate"
        inv = "Revenue growth decelerates or balance sheet deteriorates"
    elif score >= 80:
        action = "wait for pullback"
        inv = "Extended price or weakening fundamentals"
    elif score >= 70:
        action = "watchlist"
        inv = "Monitor next earnings for confirmation"
    elif score >= 60:
        action = "watchlist"
        inv = "Speculative — needs fundamental improvement"
    else:
        action = "avoid"
        inv = "Fundamental or risk concerns too high"

    return action, inv


def _confidence_level(data: dict, tech: dict, fund: dict, news: dict) -> str:
    score = 0

    # Data completeness
    missing = fund.get("missing_fundamental_fields", 0)
    if missing == 0:
        score += 3
    elif missing <= 2:
        score += 2
    elif missing <= 4:
        score += 1

    # Liquidity
    avg_vol = data.get("avg_volume") or 0
    if avg_vol >= 2_000_000:
        score += 3
    elif avg_vol >= 500_000:
        score += 2
    elif avg_vol >= 100_000:
        score += 1

    # Technical clarity
    signal = tech.get("tech_signal", "")
    if signal in ("bullish with volume", "bullish", "bearish"):
        score += 2
    elif signal in ("reversal watch", "neutral"):
        score += 1

    # News quality
    if news.get("news_count", 0) >= 3:
        score += 1

    if score >= 8:
        return "High"
    elif score >= 5:
        return "Medium"
    return "Low"


def _reasons_short(data: dict, tech: dict, news: dict, fund: dict) -> tuple[str, str]:
    reasons = []
    risks = []

    rv = data.get("rel_volume") or 0
    if rv >= 2.0:
        reasons.append(f"Unusual volume ({rv:.1f}x)")

    day_chg = data.get("day_change_pct") or 0
    if day_chg > 3:
        reasons.append(f"Strong day: +{day_chg:.1f}%")
    elif day_chg < -5:
        reasons.append(f"Large drop: {day_chg:.1f}% (reversal watch)")

    signal = tech.get("tech_signal", "")
    if "bullish" in signal:
        reasons.append(f"Technical: {signal}")

    cat = news.get("catalyst_quality", "")
    if "positive" in cat:
        reasons.append(f"Catalyst: {cat}")

    if data.get("earnings_date"):
        reasons.append(f"Earnings: {data['earnings_date']}")

    # Risks
    if tech.get("is_extended"):
        risks.append("Overextended, chasing risk")
    if data.get("dilution_flag"):
        risks.append("Dilution/offering risk")
    avg_vol = data.get("avg_volume") or 0
    if avg_vol < 500000:
        risks.append("Thin liquidity")
    if "bearish" in signal:
        risks.append("Weak technical trend")
    if fund.get("missing_fundamental_fields", 0) >= 4:
        risks.append("Limited fundamental data")

    strongest = "; ".join(reasons[:2]) if reasons else "No clear catalyst"
    biggest = "; ".join(risks[:2]) if risks else "Monitor for reversal"

    return strongest, biggest


def _reasons_long(data: dict, tech: dict, fund: dict, news: dict) -> tuple[str, str]:
    reasons = []
    risks = []

    rev_growth = data.get("revenue_growth")
    if rev_growth and rev_growth > 15:
        reasons.append(f"Revenue growth: {rev_growth:.1f}%")

    bs = fund.get("balance_sheet_signal", "")
    if "strong" in bs:
        reasons.append("Strong balance sheet")

    val = fund.get("valuation_signal", "")
    if val in ("value", "reasonable forward PE"):
        reasons.append(f"Reasonable valuation: {val}")

    cat = news.get("catalyst_quality", "")
    if "positive" in cat:
        reasons.append(f"Positive catalyst: {cat}")

    fund_sig = fund.get("fundamental_signal", "")
    if fund_sig in ("strong", "positive"):
        reasons.append(f"Fundamentals: {fund_sig}")

    # Risks
    if data.get("dilution_flag"):
        risks.append("Dilution risk")
    dtc = data.get("debt_to_cash")
    if dtc and dtc > 5:
        risks.append("High debt load")
    if rev_growth is not None and rev_growth < 0:
        risks.append(f"Declining revenue ({rev_growth:.1f}%)")
    val_sig = fund.get("valuation_signal", "")
    if "expensive" in val_sig or "high" in val_sig:
        risks.append(f"Valuation concern: {val_sig}")
    if fund.get("missing_fundamental_fields", 0) >= 4:
        risks.append("Limited fundamental data")

    strongest = "; ".join(reasons[:2]) if reasons else "No strong long-term catalyst"
    biggest = "; ".join(risks[:2]) if risks else "Monitor fundamentals"

    return strongest, biggest
