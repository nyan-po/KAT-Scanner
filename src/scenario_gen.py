"""
Scenario generation for KAT Market Screener.
Produces bull / base / bear cases from scored ticker data.
"""


def generate_scenarios(data: dict) -> list[dict]:
    """
    Generate bull, base, and bear scenarios for a scored ticker.
    Returns a list of three scenario dicts.
    """
    mode = data.get("mode", "short_term")
    score = data.get("kat_score", 50)
    price = data.get("price") or 0

    if mode == "short_term":
        returns = {
            "bull": _st_return(score, "bull"),
            "base": _st_return(score, "base"),
            "bear": _st_return(score, "bear"),
        }
        descriptions = {
            "bull": _st_bull_desc(data),
            "base": "Modest follow-through; consolidation near current levels before next directional move.",
            "bear": _st_bear_desc(data),
        }
        time_horizon = "1–5 days"
    else:
        returns = {
            "bull": _lt_return(score, "bull"),
            "base": _lt_return(score, "base"),
            "bear": _lt_return(score, "bear"),
        }
        descriptions = {
            "bull": _lt_bull_desc(data),
            "base": "Company executes in line with guidance; stock tracks earnings growth at a market multiple.",
            "bear": _lt_bear_desc(data),
        }
        time_horizon = "6–12 months"

    scenarios = []
    for label, prob in [("Bull", _bull_prob(score)), ("Base", "50%"), ("Bear", _bear_prob(score))]:
        key = label.lower()
        ret = returns[key]
        target = round(price * (1 + ret / 100), 2) if price else None
        scenarios.append({
            "scenario": label,
            "probability": prob,
            "time_horizon": time_horizon,
            "description": descriptions[key],
            "return_pct": f"{ret:+.0f}%",
            "target_price": f"${target:.2f}" if target else "N/A",
            "key_driver": (
                data.get("strongest_reason", "Momentum continuation")
                if label == "Bull"
                else data.get("biggest_risk", "Trend reversal")
                if label == "Bear"
                else "Steady execution"
            ),
        })
    return scenarios


# ---------------------------------------------------------------------------
# Return estimates
# ---------------------------------------------------------------------------

def _st_return(score: int, scenario: str) -> float:
    if scenario == "bull":
        if score >= 80: return 12.0
        if score >= 70: return 8.0
        if score >= 60: return 5.0
        return 3.0
    if scenario == "base":
        if score >= 80: return 4.0
        if score >= 70: return 2.0
        return 0.0
    # bear
    if score >= 80: return -5.0
    if score >= 70: return -8.0
    return -12.0


def _lt_return(score: int, scenario: str) -> float:
    if scenario == "bull":
        if score >= 80: return 60.0
        if score >= 70: return 40.0
        if score >= 60: return 25.0
        return 15.0
    if scenario == "base":
        if score >= 80: return 25.0
        if score >= 70: return 15.0
        if score >= 60: return 8.0
        return 0.0
    # bear
    if score >= 80: return -15.0
    if score >= 70: return -20.0
    return -30.0


# ---------------------------------------------------------------------------
# Probability labels
# ---------------------------------------------------------------------------

def _bull_prob(score: int) -> str:
    if score >= 85: return "40%"
    if score >= 75: return "30%"
    if score >= 65: return "25%"
    return "20%"


def _bear_prob(score: int) -> str:
    if score >= 85: return "10%"
    if score >= 75: return "20%"
    if score >= 65: return "25%"
    return "30%"


# ---------------------------------------------------------------------------
# Descriptions
# ---------------------------------------------------------------------------

def _st_bull_desc(data: dict) -> str:
    signal = data.get("technical_signal", "")
    rv = data.get("rel_volume") or 0
    parts = []
    if "bullish" in signal:
        parts.append("technical momentum continues")
    if rv >= 2.0:
        parts.append(f"volume surge ({rv:.1f}x) sustains buying pressure")
    parts.append("price reaches upper target range")
    return "; ".join(parts).capitalize() + "."


def _st_bear_desc(data: dict) -> str:
    risk = data.get("biggest_risk", "")
    if risk:
        return f"Risk materializes: {risk.lower()}. Price gives back recent gains."
    return "Momentum fades; price reverses and gives back recent gains."


def _lt_bull_desc(data: dict) -> str:
    rev = data.get("revenue_growth")
    fund = data.get("fundamental_signal", "")
    parts = []
    if rev and rev > 20:
        parts.append(f"revenue growth sustains above {rev:.0f}%")
    if fund in ("strong", "positive"):
        parts.append("strong fundamentals support multiple expansion")
    parts.append("sector tailwind accelerates")
    return "; ".join(parts).capitalize() + "."


def _lt_bear_desc(data: dict) -> str:
    risk = data.get("biggest_risk", "")
    if risk:
        return f"Downside case: {risk.lower()}. Macro headwinds compress the multiple."
    return "Earnings miss guidance; macro headwinds compress the multiple."
