"""
Persistent watchlist storage. Keeps a JSON file at watchlist.json
with the user's saved tickers across sessions.
"""
import json
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_PATH = Path("watchlist.json")
SNAPSHOT_DIR = Path("watchlist_snapshots")


def load_watchlist(path: Path = DEFAULT_PATH) -> list[str]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text())
        return [t.upper().strip() for t in data.get("tickers", []) if t and t.strip()]
    except Exception as e:
        logger.warning(f"Failed to load watchlist: {e}")
        return []


def save_watchlist(tickers: list[str], path: Path = DEFAULT_PATH):
    cleaned = []
    seen = set()
    for t in tickers:
        ct = t.upper().strip()
        if ct and ct not in seen:
            cleaned.append(ct)
            seen.add(ct)
    data = {"tickers": cleaned, "updated_at": datetime.now().isoformat()}
    path.write_text(json.dumps(data, indent=2))


def add_ticker(ticker: str, path: Path = DEFAULT_PATH) -> list[str]:
    wl = load_watchlist(path)
    ticker = ticker.upper().strip()
    if ticker and ticker not in wl:
        wl.append(ticker)
        save_watchlist(wl, path)
    return wl


def remove_ticker(ticker: str, path: Path = DEFAULT_PATH) -> list[str]:
    wl = load_watchlist(path)
    wl = [t for t in wl if t.upper() != ticker.upper()]
    save_watchlist(wl, path)
    return wl


def save_daily_snapshot(results: list[dict], date_str: str | None = None):
    """Save a snapshot of analyzed watchlist for day-over-day comparison."""
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
