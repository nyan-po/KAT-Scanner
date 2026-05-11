"""
Market universe builder. Fetches ticker lists from free public sources
and builds a deduplicated, yfinance-compatible ticker universe.
"""
import re
import time
import logging
import ssl
import requests
import pandas as pd
from io import StringIO

try:
    import certifi
    _SSL_VERIFY = certifi.where()
except ImportError:
    _SSL_VERIFY = False  # disable SSL verification if certifi not available

logger = logging.getLogger(__name__)

# Known ETF prefixes/suffixes to optionally filter
_ETF_KEYWORDS = {"ETF", "FUND", "TRUST", "INDEX", "ISHARES", "SPDR", "VANGUARD"}

SP500_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
NASDAQ100_URL = "https://en.wikipedia.org/wiki/Nasdaq-100"
RUSSELL2000_URL = "https://en.wikipedia.org/wiki/Russell_2000_Index"

# Fallback small-cap list (curated, actively traded as of 2025)
FALLBACK_SMALL_CAPS = [
    "APLD", "SOUN", "MARA", "RIOT", "CLSK", "BTBT", "HUT", "CIFR",
    "MGNI", "ACHR", "JOBY", "RKLB", "ASTS", "LUNR", "PL", "SPIR",
    "SMR", "NNE", "OKLO", "HYLN",
    "IONQ", "RGTI", "QUBT", "QBTS",
    "CLOV", "HIMS", "TALK",
    "KTOS", "RCAT", "AVAV",
    "LEU", "UEC", "CCJ", "DNN", "URG",
]


def _clean_ticker(ticker: str) -> str:
    ticker = ticker.strip().upper()
    ticker = re.sub(r"[^A-Z0-9.\-]", "", ticker)
    return ticker


def _is_valid_ticker(ticker: str) -> bool:
    if not ticker or len(ticker) > 10:
        return False
    return bool(re.match(r"^[A-Z]{1,5}([.\-][A-Z]{1,2})?$", ticker))


def _fetch_html(url: str) -> str:
    """Fetch HTML using requests with SSL cert handling."""
    headers = {"User-Agent": "Mozilla/5.0 (compatible; KATScreener/1.0)"}
    resp = requests.get(url, headers=headers, timeout=15, verify=_SSL_VERIFY)
    resp.raise_for_status()
    return resp.text


def _read_html_tables(url: str) -> list[pd.DataFrame]:
    html = _fetch_html(url)
    return pd.read_html(StringIO(html), header=0)


def fetch_sp500_tickers() -> list[str]:
    try:
        tables = _read_html_tables(SP500_URL)
        df = tables[0]
        col = next(
            (c for c in df.columns if "symbol" in c.lower() or "ticker" in c.lower()),
            df.columns[0],
        )
        tickers = df[col].dropna().astype(str).tolist()
        cleaned = [_clean_ticker(t) for t in tickers]
        valid = [t for t in cleaned if _is_valid_ticker(t)]
        logger.info(f"Fetched {len(valid)} S&P 500 tickers.")
        return valid
    except Exception as e:
        logger.warning(f"Failed to fetch S&P 500 tickers: {e}")
        return []


def fetch_nasdaq100_tickers() -> list[str]:
    try:
        tables = _read_html_tables(NASDAQ100_URL)
        for df in tables:
            cols_lower = [c.lower() for c in df.columns]
            if any("ticker" in c or "symbol" in c for c in cols_lower):
                col = df.columns[
                    next(
                        i
                        for i, c in enumerate(cols_lower)
                        if "ticker" in c or "symbol" in c
                    )
                ]
                tickers = df[col].dropna().astype(str).tolist()
                cleaned = [_clean_ticker(t) for t in tickers]
                valid = [t for t in cleaned if _is_valid_ticker(t)]
                logger.info(f"Fetched {len(valid)} Nasdaq-100 tickers.")
                return valid
        logger.warning("Could not find ticker column in Nasdaq-100 Wikipedia page.")
        return []
    except Exception as e:
        logger.warning(f"Failed to fetch Nasdaq-100 tickers: {e}")
        return []


def fetch_small_cap_tickers() -> list[str]:
    """Try Russell 2000 Wikipedia page; fall back to curated list."""
    try:
        tables = _read_html_tables(RUSSELL2000_URL)
        for df in tables:
            cols_lower = [c.lower() for c in df.columns]
            if any("ticker" in c or "symbol" in c for c in cols_lower):
                col = df.columns[
                    next(
                        i
                        for i, c in enumerate(cols_lower)
                        if "ticker" in c or "symbol" in c
                    )
                ]
                tickers = df[col].dropna().astype(str).tolist()
                cleaned = [_clean_ticker(t) for t in tickers]
                valid = [t for t in cleaned if _is_valid_ticker(t)]
                if valid:
                    logger.info(f"Fetched {len(valid)} small-cap tickers from Wikipedia.")
                    return valid
    except Exception as e:
        logger.warning(f"Russell 2000 Wikipedia fetch failed: {e}")

    logger.info(f"Using fallback small-cap list ({len(FALLBACK_SMALL_CAPS)} tickers).")
    return FALLBACK_SMALL_CAPS[:]


def load_custom_csv(path: str) -> list[str]:
    try:
        df = pd.read_csv(path, header=None)
        col = df.columns[0]
        tickers = df[col].dropna().astype(str).tolist()
        cleaned = [_clean_ticker(t) for t in tickers]
        valid = [t for t in cleaned if _is_valid_ticker(t)]
        logger.info(f"Loaded {len(valid)} tickers from custom CSV: {path}")
        return valid
    except Exception as e:
        logger.warning(f"Failed to load custom CSV {path}: {e}")
        return []


def build_universe(universe_cfg: dict, watchlist: list[str]) -> list[str]:
    """
    Build the full ticker universe from configured sources.
    Returns a deduplicated, validated list of tickers.
    """
    tickers: list[str] = []
    sources_tried = 0
    sources_succeeded = 0

    if universe_cfg.get("include_sp500", True):
        sources_tried += 1
        result = fetch_sp500_tickers()
        if result:
            tickers.extend(result)
            sources_succeeded += 1

    if universe_cfg.get("include_nasdaq100", True):
        sources_tried += 1
        result = fetch_nasdaq100_tickers()
        if result:
            tickers.extend(result)
            sources_succeeded += 1

    if universe_cfg.get("include_small_caps", True):
        sources_tried += 1
        result = fetch_small_cap_tickers()
        if result:
            tickers.extend(result)
            sources_succeeded += 1

    custom_csv = universe_cfg.get("custom_csv")
    if custom_csv:
        result = load_custom_csv(custom_csv)
        tickers.extend(result)

    if universe_cfg.get("include_watchlist", True) and watchlist:
        tickers.extend([_clean_ticker(t) for t in watchlist])

    if sources_succeeded == 0 and sources_tried > 0:
        logger.warning(
            "All public universe sources failed. Falling back to watchlist only."
        )
        if not watchlist:
            logger.error("No tickers available. Check your network or config watchlist.")
            return []

    # Deduplicate, preserving order
    seen = set()
    unique = []
    for t in tickers:
        ct = _clean_ticker(t)
        if ct and _is_valid_ticker(ct) and ct not in seen:
            seen.add(ct)
            unique.append(ct)

    max_tickers = universe_cfg.get("max_tickers_per_scan", 500)
    if len(unique) > max_tickers:
        logger.info(f"Trimming universe from {len(unique)} to {max_tickers} tickers.")
        unique = unique[:max_tickers]

    logger.info(f"Universe built: {len(unique)} unique tickers.")
    return unique


def build_watchlist_universe(watchlist: list[str]) -> list[str]:
    cleaned = [_clean_ticker(t) for t in watchlist]
    return [t for t in cleaned if _is_valid_ticker(t)]


def build_manual_universe(tickers: list[str]) -> list[str]:
    cleaned = [_clean_ticker(t) for t in tickers]
    return [t for t in cleaned if _is_valid_ticker(t)]


def build_csv_universe(csv_path: str) -> list[str]:
    return load_custom_csv(csv_path)
