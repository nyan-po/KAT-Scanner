"""
Technical analysis calculations from price history DataFrames.
"""
import logging
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def _ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def _sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(window=period).mean()


def calculate_technicals(price_history: pd.DataFrame, current_price: float) -> dict:
    """
    Calculate technical indicators from daily OHLCV history.
    Returns a flat dict of technical values. Missing = None.
    """
    result = {
        "ema9": None,
        "ema20": None,
        "sma50": None,
        "sma200": None,
        "above_ema9": None,
        "above_ema20": None,
        "above_sma50": None,
        "above_sma200": None,
        "return_5d": None,
        "return_20d": None,
        "is_extended": False,
        "volume_trend": None,
        "tech_signal": "insufficient data",
        "tech_notes": "",
    }

    if price_history is None or price_history.empty:
        return result

    try:
        close = price_history["Close"].dropna()
        volume = price_history["Volume"].dropna() if "Volume" in price_history else pd.Series()

        n = len(close)
        if n < 5:
            return result

        price = current_price or float(close.iloc[-1])

        if n >= 9:
            ema9 = _ema(close, 9).iloc[-1]
            result["ema9"] = round(float(ema9), 4)
            result["above_ema9"] = price > ema9

        if n >= 20:
            ema20 = _ema(close, 20).iloc[-1]
            result["ema20"] = round(float(ema20), 4)
            result["above_ema20"] = price > ema20

            ret20 = (price - float(close.iloc[-21])) / float(close.iloc[-21]) * 100 if n >= 21 else None
            result["return_20d"] = round(ret20, 2) if ret20 is not None else None

        if n >= 50:
            sma50 = _sma(close, 50).iloc[-1]
            result["sma50"] = round(float(sma50), 4)
            result["above_sma50"] = price > sma50

        if n >= 200:
            sma200 = _sma(close, 200).iloc[-1]
            result["sma200"] = round(float(sma200), 4)
            result["above_sma200"] = price > sma200

        if n >= 6:
            ret5 = (price - float(close.iloc[-6])) / float(close.iloc[-6]) * 100
            result["return_5d"] = round(ret5, 2)

        # Extended check: price > 15% above 9 EMA
        if result["ema9"] and result["ema9"] > 0:
            pct_above_ema9 = (price - result["ema9"]) / result["ema9"] * 100
            result["is_extended"] = pct_above_ema9 > 15

        # Volume trend: compare last 5 day avg vs 20 day avg
        if len(volume) >= 20:
            vol_recent = float(volume.iloc[-5:].mean())
            vol_prior = float(volume.iloc[-20:-5].mean())
            if vol_prior > 0:
                result["volume_trend"] = round(vol_recent / vol_prior, 2)

        # Derive tech signal
        result["tech_signal"] = _derive_tech_signal(result, price)
        result["tech_notes"] = _build_tech_notes(result, price)

    except Exception as e:
        logger.debug(f"Technical calculation error: {e}")

    return result


def _derive_tech_signal(t: dict, price: float) -> str:
    above9 = t.get("above_ema9")
    above20 = t.get("above_ema20")
    above50 = t.get("above_sma50")
    extended = t.get("is_extended", False)
    vol_trend = t.get("volume_trend")
    ret5 = t.get("return_5d")

    if above9 is None and above20 is None:
        return "insufficient data"

    bullish_count = sum(1 for x in [above9, above20, above50] if x is True)
    bearish_count = sum(1 for x in [above9, above20, above50] if x is False)

    if extended and bullish_count >= 2:
        return "bullish but extended"

    if bullish_count >= 2 and vol_trend and vol_trend > 1.1:
        return "bullish with volume"

    if bullish_count >= 2:
        return "bullish"

    if bearish_count >= 2 and ret5 is not None and ret5 < -5:
        # Check for reversal: price reclaiming short EMA
        if above9 is True:
            return "reversal watch"
        return "bearish"

    if bearish_count >= 2:
        return "bearish"

    return "neutral"


def _build_tech_notes(t: dict, price: float) -> str:
    notes = []
    if t.get("above_ema9") is True:
        notes.append("above 9 EMA")
    elif t.get("above_ema9") is False:
        notes.append("below 9 EMA")
    if t.get("above_ema20") is True:
        notes.append("above 20 EMA")
    elif t.get("above_ema20") is False:
        notes.append("below 20 EMA")
    if t.get("above_sma50") is True:
        notes.append("above 50 SMA")
    elif t.get("above_sma50") is False:
        notes.append("below 50 SMA")
    if t.get("is_extended"):
        notes.append("EXTENDED from 9 EMA")
    if t.get("return_5d") is not None:
        notes.append(f"5d return: {t['return_5d']:+.1f}%")
    return ", ".join(notes) if notes else ""
