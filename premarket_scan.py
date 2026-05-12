"""
KAT Pre-Market Scan — standalone script for scheduled runs.

Runs a full scan, applies filters, and posts the top picks to Discord.

Usage:
    python premarket_scan.py                        # market scan, short_term, top 15
    python premarket_scan.py --scan watchlist       # watchlist only
    python premarket_scan.py --mode long_term       # long-term scoring
    python premarket_scan.py --top 10               # limit to top 10
    python premarket_scan.py --min-grade B          # only B or better

Schedule (Mac/Linux) — runs at 8:30 AM ET Mon-Fri:
    crontab -e
    30 8 * * 1-5 cd /path/to/KAT-Scanner && python premarket_scan.py >> logs/premarket.log 2>&1

Schedule (Windows Task Scheduler):
    Action: python C:\\path\\to\\KAT-Scanner\\premarket_scan.py
    Trigger: Daily, 8:30 AM, repeat Mon-Fri
"""
import sys
import os
import argparse
import logging
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))

from src.config import load_config, get_filters, get_universe_config, get_watchlist, get_sector_mappings
from src.universe import build_universe, build_watchlist_universe
from src.data import fetch_ticker_data
from src.scoring import score_short_term, score_long_term
from src.grading import score_to_grade
from src.filters import apply_filters, sort_results, limit_results
from src.alerts import load_webhook_url, load_ping_id
from src.discord_notify import send_scan_summary

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("premarket")

GRADE_ORDER = ["A+", "A", "A-", "B+", "B", "B-", "C", "D"]


def parse_args():
    p = argparse.ArgumentParser(description="KAT pre-market scan")
    p.add_argument("--scan",      default="market",     choices=["market", "watchlist"],
                   help="Universe to scan (default: market)")
    p.add_argument("--mode",      default="short_term", choices=["short_term", "long_term"],
                   help="Scoring mode (default: short_term)")
    p.add_argument("--top",       default=15, type=int, help="Max results to show (default: 15)")
    p.add_argument("--min-grade", default=None,         help="Minimum grade to include, e.g. B")
    p.add_argument("--no-discord", action="store_true", help="Skip Discord post, print results only")
    return p.parse_args()


def run(args):
    log.info(f"=== KAT Pre-Market Scan  {datetime.now().strftime('%Y-%m-%d %H:%M')} ===")
    log.info(f"Scan: {args.scan}  |  Mode: {args.mode}  |  Top: {args.top}")

    cfg             = load_config()
    watchlist       = get_watchlist(cfg)
    sector_mappings = get_sector_mappings(cfg)
    score_fn        = score_short_term if args.mode == "short_term" else score_long_term

    # ── Build universe ─────────────────────────────────────────────────────────
    log.info("Building universe…")
    if args.scan == "watchlist":
        tickers = build_watchlist_universe(watchlist)
    else:
        tickers = build_universe(get_universe_config(cfg), watchlist)

    total = len(tickers)
    log.info(f"Scanning {total} tickers…")

    # ── Fetch + score ──────────────────────────────────────────────────────────
    results_raw = []
    failed      = []

    for i, ticker in enumerate(tickers, 1):
        if i % 50 == 0 or i == total:
            log.info(f"  {i}/{total}…")

        data = fetch_ticker_data(ticker)
        if data:
            try:
                kat_sector = next(
                    (s for s, members in sector_mappings.items() if ticker in members), None
                )
                scores = score_fn(data, kat_sector=kat_sector)
                grade  = score_to_grade(scores["kat_score"])
                results_raw.append({**data, **scores, "kat_grade": grade})
            except Exception as e:
                log.debug(f"Score failed for {ticker}: {e}")
                failed.append(ticker)
        else:
            failed.append(ticker)

        time.sleep(0.05)

    log.info(f"Scored {len(results_raw)} tickers  |  {len(failed)} failed")

    # ── Filter + sort ──────────────────────────────────────────────────────────
    f_overrides = {"max_results": args.top}
    if args.min_grade:
        f_overrides["min_grade"] = args.min_grade

    filters  = get_filters(cfg, f_overrides)
    filtered = apply_filters(results_raw, filters)
    final    = limit_results(sort_results(filtered), args.top)

    log.info(f"Passing filters: {len(final)}")

    # ── Print results ──────────────────────────────────────────────────────────
    print(f"\n{'─'*60}")
    print(f"  KAT Pre-Market  |  {args.scan} / {args.mode}  |  {datetime.now().strftime('%Y-%m-%dT%H:%M:%S')}")
    print(f"{'─'*60}")
    for i, r in enumerate(final, 1):
        print(
            f"  {i:>2}. {r['ticker']:<6} {r['kat_grade']:<3} / {r['kat_score']:.1f}"
            f"  -  {r.get('setup_type',''):<28}  ({r.get('suggested_action','')})"
        )
    print(f"\n  Scanned: {total}   Passing: {len(final)}")
    print(f"{'─'*60}\n")

    if not final:
        log.info("No results passed filters — nothing to post.")
        return

    # ── Post to Discord ────────────────────────────────────────────────────────
    if args.no_discord:
        log.info("--no-discord flag set, skipping webhook post.")
        return

    webhook_url = load_webhook_url()
    ping_id     = load_ping_id()

    if not webhook_url:
        log.warning("No webhook URL configured. Run the app and save one in the Alerts page.")
        return

    ok = send_scan_summary(
        webhook_url,
        final,
        scan_type    = args.scan,
        mode         = args.mode,
        total_scanned= total,
        ping_id      = ping_id,
    )

    if ok:
        log.info("Discord post sent successfully.")
    else:
        log.error("Discord post failed — check webhook URL.")


if __name__ == "__main__":
    run(parse_args())
