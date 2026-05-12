"""
Persistent watchlist storage. Keeps a JSON file at watchlist.json
with the user's saved tickers across sessions.

Format:
  {
    "tickers": ["NVDA", "AMD"],
    "entries": {
      "NVDA": {"added_at": "2026-05-12T10:30:00", "entry_price": 219.44},
      ...
    },
    "updated_at": "..."
  }
"""
import json
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_PATH = Path("watchlist.json")
SNAPSHOT_DIR = Path("watchlist_snapshots")


def _load_raw(path: Path = DEFAULT_PATH) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception as e:
        logger.warning(f"Failed to load watchlist: {e}")
        return {}


def _write(tickers: list[str], entries: dict, path: Path = DEFAULT_PATH):
    cleaned = []
    seen = set()
    for t in tickers:
        ct = t.upper().strip()
        if ct and ct not in seen:
            cleaned.append(ct)
            seen.add(ct)
    path.write_text(json.dumps(
        {"tickers": cleaned, "entries": entries, "updated_at": datetime.now().isoformat()},
        indent=2,
    ))


def load_watchlist(path: Path = DEFAULT_PATH) -> list[str]:
    data = _load_raw(path)
    return [t.upper().strip() for t in data.get("tickers", []) if t and t.strip()]


def load_entries(path: Path = DEFAULT_PATH) -> dict:
    """Return {TICKER: {added_at, entry_price}} for all tracked entries."""
    return _load_raw(path).get("entries", {})


def save_watchlist(tickers: list[str], path: Path = DEFAULT_PATH):
    # Preserve existing entries when saving the ticker list
    entries = _load_raw(path).get("entries", {})
    _write(tickers, entries, path)


def add_ticker(
    ticker: str,
    entry_price: float | None = None,
    path: Path = DEFAULT_PATH,
) -> list[str]:
    raw     = _load_raw(path)
    tickers = [t.upper().strip() for t in raw.get("tickers", []) if t and t.strip()]
    entries = raw.get("entries", {})
    ticker  = ticker.upper().strip()
    if ticker and ticker not in tickers:
        tickers.append(ticker)
        if ticker not in entries:
            entries[ticker] = {
                "added_at":    datetime.now().isoformat(timespec="seconds"),
                "entry_price": entry_price,
            }
        _write(tickers, entries, path)
    return tickers


def remove_ticker(ticker: str, path: Path = DEFAULT_PATH) -> list[str]:
    raw     = _load_raw(path)
    tickers = [t for t in raw.get("tickers", []) if t.upper() != ticker.upper()]
    entries = raw.get("entries", {})
    entries.pop(ticker.upper(), None)
    _write(tickers, entries, path)
    return [t.upper().strip() for t in tickers if t and t.strip()]


def save_daily_snapshot(results: list[dict], date_str: str | None = None):
    SNAPSHOT_DIR.mkdir(exist_ok=True)
    if not date_str:
        date_str = datetime.now().strftime("%Y-%m-%d")
    path = SNAPSHOT_DIR / f"{date_str}.json"
    rows = [
        {k: (list(v) if isinstance(v, (list, tuple)) else v)
         for k, v in r.items()
         if k != "price_history"}
        for r in results
    ]
    path.write_text(json.dumps({"date": date_str, "results": rows}, indent=2, default=str))
    return path


def load_latest_snapshot() -> dict | None:
    if not SNAPSHOT_DIR.exists():
        return None
    files = sorted(SNAPSHOT_DIR.glob("*.json"), reverse=True)
    if not files:
        return None
    try:
        return json.loads(files[0].read_text())
    except Exception:
        return None
