"""
Fundamental analysis helpers. Derives signals and scores from fetched data.
"""
import logging

logger = logging.getLogger(__name__)


def analyze_fundamentals(data: dict) -> dict:
    """
    Derive fundamental signals from raw data dict.
    Returns a dict of fundamental signals and a fundamental score (0-100).
    """
    result = {
        "fundamental_signal": "neutral",
        "fundamental_notes": "",
        "valuation_signal": "unknown",
        "balance_sheet_signal": "unknown",
        "fundamental_score": 50,
    }

    notes = []
    score = 50
    missing_fields = 0
    total_fields = 8  # key fundamental fields

    revenue_growth = data.get("revenue_growth")
    earnings_growth = data.get("earnings_growth")
    pe = data.get("pe")
    forward_pe = data.get("forward_pe")
    ps_ratio = data.get("ps_ratio")
    gross_margin = data.get("gross_margin")
    operating_margin = data.get("operating_margin")
    free_cash_flow = data.get("free_cash_flow")
    total_cash = data.get("total_cash")
    total_debt = data.get("total_debt")
    debt_to_cash = data.get("debt_to_cash")
    market_cap = data.get("market_cap")

    # Revenue growth
    if revenue_growth is not None:
        if revenue_growth > 30:
            score += 15
            notes.append(f"Strong revenue growth: {revenue_growth:.1f}%")
        elif revenue_growth > 15:
            score += 8
            notes.append(f"Good revenue growth: {revenue_growth:.1f}%")
        elif revenue_growth > 5:
            score += 3
            notes.append(f"Moderate revenue growth: {revenue_growth:.1f}%")
        elif revenue_growth < 0:
            score -= 10
            notes.append(f"Negative revenue growth: {revenue_growth:.1f}%")
    else:
        missing_fields += 1

    # Earnings growth
    if earnings_growth is not None:
        if earnings_growth > 30:
            score += 8
        elif earnings_growth > 10:
            score += 4
        elif earnings_growth < -20:
            score -= 8
    else:
        missing_fields += 1

    # Valuation
    val_signal = "unknown"
    if pe is not None:
        if pe < 0:
            notes.append("Negative PE (unprofitable)")
            val_signal = "unprofitable"
        elif pe < 20:
            score += 8
            notes.append(f"Reasonable PE: {pe:.1f}x")
            val_signal = "value"
        elif pe < 40:
            score += 3
            val_signal = "fair"
        elif pe < 80:
            score -= 3
            val_signal = "elevated"
            notes.append(f"Elevated PE: {pe:.1f}x")
        else:
            score -= 8
            val_signal = "expensive"
            notes.append(f"Expensive PE: {pe:.1f}x")
    elif forward_pe is not None:
        if forward_pe < 20:
            score += 5
            val_signal = "reasonable forward PE"
        elif forward_pe > 60:
            score -= 5
            val_signal = "high forward PE"
        else:
            val_signal = "moderate"
    elif ps_ratio is not None:
        if ps_ratio < 5:
            score += 5
            val_signal = "low P/S"
        elif ps_ratio > 30:
            score -= 5
            val_signal = "high P/S"
        else:
            val_signal = "moderate P/S"
    else:
        missing_fields += 1
        # Do NOT heavily penalize high-growth companies with no PE
        # Only a small confidence reduction
        val_signal = "no valuation data"

    result["valuation_signal"] = val_signal

    # Margins
    if gross_margin is not None:
        if gross_margin > 60:
            score += 5
        elif gross_margin > 40:
            score += 2
        elif gross_margin < 10:
            score -= 5
    else:
        missing_fields += 1

    if operating_margin is not None:
        if operating_margin > 20:
            score += 5
        elif operating_margin > 10:
            score += 2
        elif operating_margin < -20:
            score -= 8
            notes.append("Deep operating losses")
    else:
        missing_fields += 1

    # Balance sheet
    bs_signal = "unknown"
    if total_cash is not None and total_debt is not None:
        if debt_to_cash is not None:
            if debt_to_cash < 0.5:
                score += 8
                bs_signal = "strong"
                notes.append("Low debt vs cash")
            elif debt_to_cash < 2:
                score += 3
                bs_signal = "manageable"
            elif debt_to_cash < 5:
                score -= 5
                bs_signal = "leveraged"
                notes.append("High debt vs cash")
            else:
                score -= 12
                bs_signal = "stressed"
                notes.append("Very high debt vs cash")
    elif total_cash is not None and total_debt is None:
        score += 3
        bs_signal = "cash-positive (debt unknown)"
    else:
        missing_fields += 2
        bs_signal = "balance sheet unknown"

    result["balance_sheet_signal"] = bs_signal

    # FCF
    if free_cash_flow is not None:
        if free_cash_flow > 0:
            score += 5
        elif free_cash_flow < 0:
            score -= 3
    else:
        missing_fields += 1

    # Missing data penalty: mild
    if missing_fields > 0:
        penalty = min(missing_fields * 2, 10)
        score -= penalty

    score = max(0, min(100, score))
    result["fundamental_score"] = score

    # Overall signal
    if score >= 70:
        result["fundamental_signal"] = "strong"
    elif score >= 55:
        result["fundamental_signal"] = "positive"
    elif score >= 40:
        result["fundamental_signal"] = "neutral"
    elif score >= 25:
        result["fundamental_signal"] = "weak"
    else:
        result["fundamental_signal"] = "poor"

    result["fundamental_notes"] = "; ".join(notes) if notes else "No standout fundamental factors"
    result["missing_fundamental_fields"] = missing_fields

    return result
