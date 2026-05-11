"""
Data fetching layer. Downloads price, info, and history from yfinance.
All fields are fetched defensively — missing data returns None, never raises.
"""
import logging
import time
import yfinance as yf
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)

_NA = None  # sentinel for missing data


def _safe_get(d: dict, key: str, default=None):
    val = d.get(key, default)
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return default
    return val


def fetch_ticker_data(ticker: str, retries: int = 2) -> dict | None:
    """
    Fetch all available data for a single ticker.
    Returns a dict of fields, or None if the ticker is completely unreachable.
    """
    for attempt in range(retries + 1):
        try:
            yf_ticker = yf.Ticker(ticker)
            info = yf_ticker.info or {}

            if not info or info.get("regularMarketPrice") is None and info.get("currentPrice") is None:
                # May be a bad ticker; try fast_info
                try:
                    fi = yf_ticker.fast_info
                    price = getattr(fi, "last_price", None)
                    if price is None:
                        logger.debug(f"No price data for {ticker}, skipping.")
                        return None
                except Exception:
                    return None

            price = (
                _safe_get(info, "currentPrice")
                or _safe_get(info, "regularMarketPrice")
                or _safe_get(info, "navPrice")
            )

            if price is None:
                try:
                    fi = yf_ticker.fast_info
                    price = getattr(fi, "last_price", None)
                except Exception:
                    pass

            if price is None:
                return None

            # Price history for technicals
            hist = pd.DataFrame()
            try:
                hist = yf_ticker.history(period="1y", interval="1d", auto_adjust=True)
            except Exception as e:
                logger.debug(f"History fetch failed for {ticker}: {e}")

            # News
            news_items = []
            try:
                raw_news = yf_ticker.news or []
                for n in raw_news[:5]:
                    title = n.get("title", "")
                    if title:
                        news_items.append(title)
            except Exception:
                pass

            # Earnings date
            earnings_date = _NA
            try:
                cal = yf_ticker.calendar
                if cal is not None and not cal.empty:
                    if "Earnings Date" in cal.index:
                        ed = cal.loc["Earnings Date"]
                        if hasattr(ed, "iloc"):
                            earnings_date = str(ed.iloc[0].date()) if not pd.isna(ed.iloc[0]) else _NA
                        else:
                            earnings_date = str(ed)
            except Exception:
                pass

            # Float shares
            float_shares = _safe_get(info, "floatShares")

            avg_vol = _safe_get(info, "averageVolume") or _safe_get(info, "averageVolume10days")
            volume = _safe_get(info, "volume") or _safe_get(info, "regularMarketVolume")

            rel_volume = _NA
            if avg_vol and avg_vol > 0 and volume is not None:
                rel_volume = round(volume / avg_vol, 2)

            market_cap = _safe_get(info, "marketCap")
            prev_close = _safe_get(info, "previousClose") or _safe_get(info, "regularMarketPreviousClose")
            day_change_pct = _NA
            if price and prev_close and prev_close > 0:
                day_change_pct = round((price - prev_close) / prev_close * 100, 2)

            week52_high = _safe_get(info, "fiftyTwoWeekHigh")
            week52_low = _safe_get(info, "fiftyTwoWeekLow")
            dist_from_52w_high = _NA
            if price and week52_high and week52_high > 0:
                dist_from_52w_high = round((price - week52_high) / week52_high * 100, 2)

            # Revenue/earnings
            revenue_growth = _safe_get(info, "revenueGrowth")
            earnings_growth = _safe_get(info, "earningsGrowth")
            if revenue_growth is not None:
                revenue_growth = round(revenue_growth * 100, 2)
            if earnings_growth is not None:
                earnings_growth = round(earnings_growth * 100, 2)

            # Valuation
            pe = _safe_get(info, "trailingPE")
            forward_pe = _safe_get(info, "forwardPE")
            ps_ratio = _safe_get(info, "priceToSalesTrailing12Months")
            eps = _safe_get(info, "trailingEps")
            gross_margin = _safe_get(info, "grossMargins")
            operating_margin = _safe_get(info, "operatingMargins")
            if gross_margin is not None:
                gross_margin = round(gross_margin * 100, 2)
            if operating_margin is not None:
                operating_margin = round(operating_margin * 100, 2)

            # Balance sheet
            free_cash_flow = _safe_get(info, "freeCashflow")
            total_cash = _safe_get(info, "totalCash")
            total_debt = _safe_get(info, "totalDebt")
            debt_to_cash = _NA
            if total_cash and total_cash > 0 and total_debt is not None:
                debt_to_cash = round(total_debt / total_cash, 2)

            short_percent = _safe_get(info, "shortPercentOfFloat")
            if short_percent is not None:
                short_percent = round(short_percent * 100, 2)

            return {
                "ticker": ticker,
                "company_name": _safe_get(info, "longName") or _safe_get(info, "shortName") or ticker,
                "sector": _safe_get(info, "sector") or "Unknown",
                "industry": _safe_get(info, "industry") or "Unknown",
                "quote_type": _safe_get(info, "quoteType") or "EQUITY",
                "price": price,
                "market_cap": market_cap,
                "float_shares": float_shares,
                "volume": volume,
                "avg_volume": avg_vol,
                "rel_volume": rel_volume,
                "day_change_pct": day_change_pct,
                "week52_high": week52_high,
                "week52_low": week52_low,
                "dist_from_52w_high_pct": dist_from_52w_high,
                "revenue_growth": revenue_growth,
                "earnings_growth": earnings_growth,
                "eps": eps,
                "pe": pe,
                "forward_pe": forward_pe,
                "ps_ratio": ps_ratio,
                "gross_margin": gross_margin,
                "operating_margin": operating_margin,
                "free_cash_flow": free_cash_flow,
                "total_cash": total_cash,
                "total_debt": total_debt,
                "debt_to_cash": debt_to_cash,
                "short_percent_float": short_percent,
                "earnings_date": earnings_date,
                "news_headlines": news_items,
                "price_history": hist,
            }

        except Exception as e:
            if attempt < retries:
                time.sleep(1)
                continue
            logger.warning(f"Failed to fetch data for {ticker}: {e}")
            return None

    return None


def fetch_batch(tickers: list[str], show_progress: bool = True) -> dict[str, dict]:
    """
    Fetch data for a list of tickers, returning a dict keyed by ticker.
    Failed tickers are skipped and counted.
    """
    results = {}
    failed = []
    total = len(tickers)

    for i, ticker in enumerate(tickers, 1):
        if show_progress and (i % 25 == 0 or i == 1 or i == total):
            print(f"  [Progress] Scanning {i}/{total} tickers...", flush=True)

        data = fetch_ticker_data(ticker)
        if data:
            results[ticker] = data
        else:
            failed.append(ticker)

        # Small delay to be polite to yfinance / avoid rate-limiting
        time.sleep(0.05)

    if failed:
        logger.info(f"Failed tickers ({len(failed)}): {', '.join(failed[:20])}" +
                    (" ..." if len(failed) > 20 else ""))

    return results
