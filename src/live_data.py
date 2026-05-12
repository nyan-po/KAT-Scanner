"""
Lightweight live-data fetcher for intraday watchlist updates.
Uses yf.download() to batch-fetch latest prices much faster than per-ticker .info calls.
"""
import logging
from datetime import datetime

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)


def fetch_live_quotes(tickers: list[str], intraday: bool = True) -> dict[str, dict]:
    """
    Batch-fetch the latest price, % change, volume, and rel volume for a list
    of tickers. Optimised for speed — ideal for repeated intraday refreshes.

    intraday=True uses 1-minute bars (last 2 trading days) for true intraday price.
    intraday=False uses daily bars only (faster, end-of-day data).
    """
    if not tickers:
        return {}

    period   = "5d" if intraday else "1mo"
    interval = "1m" if intraday else "1d"

    try:
        df = yf.download(
            tickers=" ".join(tickers),
            period=period,
            interval=interval,
            progress=False,
            group_by="ticker",
            threads=True,
            auto_adjust=True,
        )
    except Exception as e:
        logger.warning(f"Batch yf.download failed: {e}")
        return {}

    if df is None or df.empty:
        return {}

    results = {}
    is_multi = len(tickers) > 1

    # Also fetch daily bars to compute prev_close consistently if intraday
    daily_df = None
    if intraday:
        try:
            daily_df = yf.download(
                tickers=" ".join(tickers),
                period="5d",
                interval="1d",
                progress=False,
                group_by="ticker",
                threads=True,
                auto_adjust=True,
            )
        except Exception:
            daily_df = None

    now_iso = datetime.now().isoformat(timespec="seconds")

    for ticker in tickers:
        try:
            tdf = df[ticker] if is_multi else df
            if tdf is None or tdf.empty:
                continue
            tdf = tdf.dropna(subset=["Close"])
            if tdf.empty:
                continue

            current = tdf.iloc[-1]
            price = float(current["Close"])
            cur_vol = float(current["Volume"]) if not pd.isna(current["Volume"]) else 0

            # Previous close from daily bars
            prev_close = None
            today_volume = None
            avg_volume = None

            if daily_df is not None and not daily_df.empty:
                try:
                    ddf = daily_df[ticker] if is_multi else daily_df
                    ddf = ddf.dropna(subset=["Close"])
                    if len(ddf) >= 2:
                        prev_close = float(ddf["Close"].iloc[-2])
                        today_volume = float(ddf["Volume"].iloc[-1]) if not pd.isna(ddf["Volume"].iloc[-1]) else 0
                        avg_volume = float(ddf["Volume"].iloc[-21:-1].mean()) if len(ddf) >= 20 \
                            else float(ddf["Volume"].iloc[:-1].mean())
                except Exception:
                    pass

            if prev_close is None:
                # fall back to first row of intraday df
                prev_close = float(tdf["Close"].iloc[0])

            day_chg = ((price - prev_close) / prev_close * 100) if prev_close > 0 else 0

            # For intraday volume, sum the 1-min bars from "today"
            if intraday and today_volume is None:
                try:
                    today_volume = float(tdf["Volume"].sum())
                except Exception:
                    today_volume = cur_vol

            rel_vol = None
            if avg_volume and avg_volume > 0 and today_volume:
                rel_vol = round(today_volume / avg_volume, 2)

            results[ticker] = {
                "ticker": ticker,
                "price": round(price, 2),
                "prev_close": round(prev_close, 2),
                "day_change_pct": round(day_chg, 2),
                "volume": int(today_volume) if today_volume else None,
                "avg_volume": int(avg_volume) if avg_volume else None,
                "rel_volume": rel_vol,
                "fetched_at": now_iso,
            }
        except Exception as e:
            logger.debug(f"Live quote failed for {ticker}: {e}")
            continue

    return results
