#!/usr/bin/env python3
"""
KAT Market Screener - Main entry point.

Default: python main.py -> market scan, short_term mode.
"""
import argparse
import logging
import os
import sys
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(__file__))

from src.config import load_config, get_filters, get_universe_config, get_watchlist, get_sector_mappings, get_output_config
from src.universe import build_universe, build_watchlist_universe, build_manual_universe, build_csv_universe
from src.data import fetch_batch
from src.scoring import score_short_term, score_long_term
from src.grading import score_to_grade
from src.filters import apply_filters, sort_results, limit_results
from src.output import (
    print_scan_header,
    print_results_table,
    save_csv,
    save_json,
    print_failure_summary,
)

logging.basicConfig(
    level=logging.WARNING,
    format="%(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("kat")


def parse_args():
    parser = argparse.ArgumentParser(
        description="KAT Market Screener — rules-based market-wide stock screener",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py
  python main.py --scan market --mode short_term
  python main.py --scan market --mode long_term
  python main.py --scan watchlist --mode short_term
  python main.py --ticker NVDA --mode long_term
  python main.py --ticker NVDA AAPL MSFT --mode short_term
  python main.py --csv tickers.csv --mode short_term
  python main.py --scan market --mode short_term --min-grade A-
  python main.py --scan market --mode long_term --min-market-cap 500000000
  python main.py --scan market --mode short_term --min-rel-volume 2.0 --max-results 20
        """,
    )

    parser.add_argument(
        "--scan", choices=["market", "watchlist"],
        help="Scan type: market (default) or watchlist",
    )
    parser.add_argument(
        "--ticker", nargs="+", metavar="TICKER",
        help="One or more ticker symbols to analyze",
    )
    parser.add_argument(
        "--csv", metavar="FILE",
        help="Path to CSV file containing ticker symbols",
    )
    parser.add_argument(
        "--mode", choices=["short_term", "long_term"], default=None,
        help="Analysis mode (default from config)",
    )
    parser.add_argument(
        "--config", default=None,
        help="Path to config.yaml (default: ./config.yaml)",
    )

    # Filter overrides
    parser.add_argument("--min-price", type=float, default=None)
    parser.add_argument("--max-price", type=float, default=None)
    parser.add_argument("--min-market-cap", type=float, default=None)
    parser.add_argument("--min-avg-volume", type=float, default=None)
    parser.add_argument("--min-rel-volume", type=float, default=None)
    parser.add_argument("--min-revenue-growth", type=float, default=None)
    parser.add_argument("--max-pe", type=float, default=None)
    parser.add_argument("--earnings-within-days", type=int, default=None)
    parser.add_argument("--min-grade", type=str, default=None,
                        help="Minimum KAT grade (e.g. A-, B+, B)")
    parser.add_argument("--max-results", type=int, default=None)
    parser.add_argument("--exclude-etfs", action="store_true", default=None)
    parser.add_argument("--exclude-low-priced", action="store_true", default=None)
    parser.add_argument("--verbose", action="store_true", default=False,
                        help="Print every ticker as it is fetched with price and %% change")

    return parser.parse_args()


def determine_scan_mode(args, cfg: dict) -> tuple[str, str, list[str]]:
    """
    Returns (scan_type, mode, ticker_list).
    """
    default = cfg.get("default_scan", {})
    mode = args.mode or default.get("mode", "short_term")

    # Manual tickers take priority
    if args.ticker:
        return "manual", mode, args.ticker

    # CSV takes next priority
    if args.csv:
        return "csv", mode, []

    # Explicit scan flag
    if args.scan:
        return args.scan, mode, []

    # Default from config
    scan = default.get("scan", "market")
    return scan, mode, []


def build_ticker_list(scan_type: str, tickers: list[str], csv_path: str | None,
                      cfg: dict) -> list[str]:
    universe_cfg = get_universe_config(cfg)
    watchlist = get_watchlist(cfg)

    if scan_type == "manual":
        return build_manual_universe(tickers)
    elif scan_type == "csv":
        return build_csv_universe(csv_path)
    elif scan_type == "watchlist":
        return build_watchlist_universe(watchlist)
    else:  # market
        print("\n  Building market universe...", flush=True)
        return build_universe(universe_cfg, watchlist)


def get_kat_sector(ticker: str, sector_mappings: dict) -> str | None:
    for kat_sector, members in sector_mappings.items():
        if ticker in members:
            return kat_sector
    return None


def run_screener(tickers: list[str], mode: str, scan_type: str, cfg: dict,
                 filter_overrides: dict, verbose: bool = False) -> list[dict]:
    sector_mappings = get_sector_mappings(cfg)
    filters = get_filters(cfg, filter_overrides)

    print(f"\n  Fetching data for {len(tickers)} tickers...", flush=True)
    raw_data = fetch_batch(tickers, show_progress=not verbose, verbose=verbose)

    total_scanned = len(tickers)
    failed = [t for t in tickers if t not in raw_data]

    print(f"\n  Scoring {len(raw_data)} tickers (mode: {mode})...", flush=True)
    results = []

    score_fn = score_short_term if mode == "short_term" else score_long_term

    for ticker, data in raw_data.items():
        try:
            kat_sector = get_kat_sector(ticker, sector_mappings)
            scores = score_fn(data, kat_sector=kat_sector)
            grade = score_to_grade(scores["kat_score"])

            result = {**data, **scores, "kat_grade": grade}
            # Remove raw price_history from result for output (kept internally for scoring)
            results.append(result)
        except Exception as e:
            logger.warning(f"Scoring failed for {ticker}: {e}")
            failed.append(ticker)

    # Apply filters
    filtered = apply_filters(results, filters)
    sorted_results = sort_results(filtered, key="kat_score", ascending=False)
    max_results = filter_overrides.get("max_results") or filters.get("max_results")
    final = limit_results(sorted_results, max_results)

    print_scan_header(scan_type, mode, total_scanned, len(final))
    print_results_table(final, filters=filters)

    # Save outputs
    output_cfg = get_output_config(cfg)
    meta = {
        "scan_type": scan_type,
        "mode": mode,
        "timestamp": datetime.now().isoformat(),
        "tickers_scanned": total_scanned,
        "tickers_passed": len(final),
        "filters_applied": filters,
    }
    if output_cfg.get("save_csv", True):
        save_csv(final, output_cfg.get("csv_path", "screener_results.csv"))
    if output_cfg.get("save_json", True):
        save_json(final, output_cfg.get("json_path", "screener_results.json"), meta=meta)

    print_failure_summary(failed)

    return final


def main():
    args = parse_args()
    cfg = load_config(args.config)

    scan_type, mode, manual_tickers = determine_scan_mode(args, cfg)

    tickers = build_ticker_list(
        scan_type,
        manual_tickers,
        args.csv,
        cfg,
    )

    if not tickers:
        print("ERROR: No tickers available to scan. Check your config or input.")
        sys.exit(1)

    # Build CLI filter overrides dict
    filter_overrides = {}
    if args.min_price is not None:
        filter_overrides["min_price"] = args.min_price
    if args.max_price is not None:
        filter_overrides["max_price"] = args.max_price
    if args.min_market_cap is not None:
        filter_overrides["min_market_cap"] = args.min_market_cap
    if args.min_avg_volume is not None:
        filter_overrides["min_avg_volume"] = args.min_avg_volume
    if args.min_rel_volume is not None:
        filter_overrides["min_relative_volume"] = args.min_rel_volume
    if args.min_revenue_growth is not None:
        filter_overrides["min_revenue_growth"] = args.min_revenue_growth
    if args.max_pe is not None:
        filter_overrides["max_pe"] = args.max_pe
    if args.earnings_within_days is not None:
        filter_overrides["earnings_within_days"] = args.earnings_within_days
    if args.min_grade is not None:
        filter_overrides["min_grade"] = args.min_grade
    if args.max_results is not None:
        filter_overrides["max_results"] = args.max_results
    if args.exclude_etfs:
        filter_overrides["exclude_etfs"] = True
    if args.exclude_low_priced:
        filter_overrides["exclude_low_priced"] = True

    run_screener(tickers, mode, scan_type, cfg, filter_overrides, verbose=args.verbose)


if __name__ == "__main__":
    main()
