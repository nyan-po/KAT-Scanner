"""
News and catalyst analysis. Uses yfinance news headlines (already fetched in data.py).
No paid APIs required for MVP.
"""
import logging
import re

logger = logging.getLogger(__name__)

# Keywords that suggest a positive catalyst
BULLISH_KEYWORDS = [
    "beat", "beats", "record", "record high", "growth", "revenue growth", "profit",
    "partnership", "contract", "deal", "acquisition", "merger", "buyout", "FDA",
    "approval", "approved", "launch", "launches", "upgrade", "raised", "raises",
    "dividend", "buyback", "upbeat", "guidance", "strong", "exceed", "exceeds",
    "breakthrough", "award", "winner", "positive", "surpass", "momentum", "rally",
    "expand", "expansion", "join", "selected", "ai", "artificial intelligence",
    "investment", "funding",
]

# Keywords that suggest a negative catalyst
BEARISH_KEYWORDS = [
    "miss", "misses", "missed", "loss", "losses", "cut", "cuts", "downgrade",
    "lawsuit", "investigation", "sec", "fraud", "warning", "concern", "decline",
    "decline", "layoffs", "layoff", "recall", "delay", "delays", "bankruptcy",
    "chapter 11", "short seller", "short-seller", "dilution", "offering",
    "secondary offering", "debt", "default", "downward", "lower guidance",
    "weak", "disappointing", "failed", "failure", "revoke", "suspend",
]

DILUTION_KEYWORDS = [
    "offering", "secondary", "dilut", "shares sold", "at-the-market", "atm offering",
    "registered direct", "public offering", "private placement",
]


def analyze_news(headlines: list[str], earnings_date: str | None = None) -> dict:
    """
    Analyze news headlines for catalyst quality.
    Returns a dict with catalyst_summary, catalyst_score (0-20), dilution_flag.
    """
    result = {
        "catalyst_summary": "No recent news found",
        "catalyst_score": 5,  # conservative baseline
        "dilution_flag": False,
        "news_count": 0,
        "catalyst_quality": "none",
    }

    if not headlines:
        return result

    result["news_count"] = len(headlines)
    bull_hits = 0
    bear_hits = 0
    dilution_hits = 0
    matched_headlines = []

    for headline in headlines:
        hl_lower = headline.lower()

        for kw in BULLISH_KEYWORDS:
            if kw in hl_lower:
                bull_hits += 1
                matched_headlines.append(f"[+] {headline}")
                break

        for kw in BEARISH_KEYWORDS:
            if kw in hl_lower:
                bear_hits += 1
                if not any(headline in h for h in matched_headlines):
                    matched_headlines.append(f"[-] {headline}")
                break

        for kw in DILUTION_KEYWORDS:
            if kw in hl_lower:
                dilution_hits += 1
                result["dilution_flag"] = True
                break

    # Score: max 20
    net = bull_hits - bear_hits
    if net >= 3:
        score = 18
        quality = "strong positive"
    elif net == 2:
        score = 15
        quality = "positive"
    elif net == 1:
        score = 12
        quality = "mildly positive"
    elif net == 0 and bull_hits > 0:
        score = 8
        quality = "mixed"
    elif net == 0 and bear_hits == 0:
        score = 7
        quality = "neutral"
    elif net == -1:
        score = 4
        quality = "mildly negative"
    else:
        score = 2
        quality = "negative"

    # Dilution penalty
    if result["dilution_flag"]:
        score = max(0, score - 6)
        quality += " / dilution risk"

    result["catalyst_score"] = score
    result["catalyst_quality"] = quality

    # Build summary
    if matched_headlines:
        summary = headlines[0][:120]
        if len(headlines) > 1:
            summary += f" (+{len(headlines)-1} more)"
        result["catalyst_summary"] = summary
    else:
        result["catalyst_summary"] = headlines[0][:120] if headlines else "No recent news found"

    return result


def score_earnings_timing(earnings_date: str | None, from_date: str | None = None) -> int:
    """
    Score based on proximity to earnings. Max 15 points.
    """
    if earnings_date is None:
        return 3

    try:
        from datetime import date, datetime
        today = date.today()
        ed = datetime.strptime(earnings_date, "%Y-%m-%d").date()
        days_away = (ed - today).days

        if 0 <= days_away <= 5:
            return 15  # Imminent catalyst
        elif 6 <= days_away <= 14:
            return 12
        elif 15 <= days_away <= 30:
            return 9
        elif 31 <= days_away <= 60:
            return 5
        else:
            return 3
    except Exception:
        return 3
