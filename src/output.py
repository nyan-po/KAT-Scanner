"""
Terminal output, CSV, and JSON export for screener results.
"""
import json
import logging
import os
from datetime import datetime
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

try:
    from rich.console import Console
    from rich.table import Table
    from rich import box
    _RICH = True
except ImportError:
    _RICH = False
    logger.warning("rich not installed, falling back to plain text output.")


def _fmt(val: Any, decimals: int = 2, suffix: str = "") -> str:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return "N/A"
    if isinstance(val, float):
        return f"{val:.{decimals}f}{suffix}"
    return str(val)


def _fmt_currency(val: Any) -> str:
    if val is None:
        return "N/A"
    try:
        v = float(val)
        if v >= 1_000_000_000_000:
            return f"${v/1_000_000_000_000:.2f}T"
        elif v >= 1_000_000_000:
            return f"${v/1_000_000_000:.2f}B"
        elif v >= 1_000_000:
            return f"${v/1_000_000:.2f}M"
        return f"${v:.0f}"
    except (TypeError, ValueError):
        return "N/A"


def _grade_style(grade: str) -> str:
    if not _RICH:
        return grade
    styles = {
        "A+": "bold bright_green",
        "A":  "bold green",
        "A-": "green",
        "B+": "bold cyan",
        "B":  "cyan",
        "B-": "yellow",
        "C":  "bold yellow",
        "D":  "bold red",
    }
    return styles.get(grade, "white")


def _action_style(action: str) -> str:
    action_lower = action.lower()
    if "buy" in action_lower:
        return "bold bright_green"
    elif "wait" in action_lower:
        return "bold yellow"
    elif "watchlist" in action_lower:
        return "cyan"
    elif "avoid" in action_lower:
        return "bold red"
    return "white"


def _confidence_style(conf: str) -> str:
    if conf == "High":
        return "bold green"
    elif conf == "Medium":
        return "yellow"
    return "dim"


def print_scan_header(scan_type: str, mode: str, total_scanned: int, total_passed: int):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if _RICH:
        console = Console()
        console.rule(f"[bold blue]KAT Market Screener[/bold blue]")
        console.print(
            f"  Scan: [bold]{scan_type}[/bold]  |  "
            f"Mode: [bold]{mode}[/bold]  |  "
            f"Timestamp: {ts}",
            style="dim",
        )
        console.print(
            f"  Tickers scanned: [bold]{total_scanned}[/bold]  |  "
            f"Passing filters: [bold green]{total_passed}[/bold green]",
        )
        console.rule()
    else:
        print("=" * 80)
        print("  KAT Market Screener")
        print(f"  Scan: {scan_type}  |  Mode: {mode}  |  Timestamp: {ts}")
        print(f"  Tickers scanned: {total_scanned}  |  Passing filters: {total_passed}")
        print("=" * 80)


def print_results_table(results: list[dict], filters: dict | None = None):
    if not results:
        print("\n  No results passed filters.")
        if filters:
            active = {k: v for k, v in filters.items() if v is not None and v is not False}
            if active:
                print("  Active filters that may be too restrictive:")
                for k, v in active.items():
                    print(f"    --{k.replace('_', '-')} {v}")
                print("  Try relaxing filters, e.g.: --min-grade D  or remove --min-rel-volume")
        return

    if _RICH:
        _print_rich_table(results)
    else:
        _print_plain_table(results)


def _print_rich_table(results: list[dict]):
    console = Console()
    table = Table(
        box=box.SIMPLE_HEAVY,
        show_header=True,
        header_style="bold blue",
        show_lines=False,
        expand=False,
    )

    cols = [
        ("Rank", "right", 4),
        ("Ticker", "left", 7),
        ("Company", "left", 22),
        ("Price", "right", 8),
        ("% Chg", "right", 7),
        ("RelVol", "right", 7),
        ("Mkt Cap", "right", 9),
        ("Score", "right", 6),
        ("Grade", "center", 6),
        ("Setup", "left", 22),
        ("Action", "left", 14),
        ("Conf", "center", 6),
        ("Strongest Reason", "left", 30),
        ("Biggest Risk", "left", 25),
    ]

    for name, justify, _ in cols:
        table.add_column(name, justify=justify, no_wrap=False)

    for rank, r in enumerate(results, 1):
        grade = r.get("kat_grade", "D")
        action = r.get("suggested_action", "avoid")
        conf = r.get("confidence", "Low")
        day_chg = r.get("day_change_pct")
        chg_str = f"{day_chg:+.1f}%" if day_chg is not None else "N/A"
        chg_style = "green" if (day_chg or 0) > 0 else "red"

        company = (r.get("company_name") or "")[:20]
        setup = (r.get("setup_type") or "")[:20]
        reason = (r.get("strongest_reason") or "")[:28]
        risk = (r.get("biggest_risk") or "")[:23]

        table.add_row(
            str(rank),
            r.get("ticker", ""),
            company,
            f"${_fmt(r.get('price'), 2)}",
            f"[{chg_style}]{chg_str}[/{chg_style}]",
            _fmt(r.get("rel_volume"), 1),
            _fmt_currency(r.get("market_cap")),
            str(r.get("kat_score", 0)),
            f"[{_grade_style(grade)}]{grade}[/{_grade_style(grade)}]",
            setup,
            f"[{_action_style(action)}]{action}[/{_action_style(action)}]",
            f"[{_confidence_style(conf)}]{conf}[/{_confidence_style(conf)}]",
            reason,
            risk,
        )

    console.print(table)


def _print_plain_table(results: list[dict]):
    headers = [
        "Rank", "Ticker", "Company", "Price", "%Chg", "RelVol",
        "MktCap", "Score", "Grade", "Setup", "Action", "Conf",
        "StrongestReason", "BiggestRisk",
    ]
    widths = [4, 7, 20, 8, 7, 7, 10, 6, 6, 20, 14, 6, 28, 24]
    header_line = "  ".join(h.ljust(w) for h, w in zip(headers, widths))
    print(header_line)
    print("-" * len(header_line))

    for rank, r in enumerate(results, 1):
        grade = r.get("kat_grade", "D")
        action = r.get("suggested_action", "avoid")
        conf = r.get("confidence", "Low")
        day_chg = r.get("day_change_pct")
        chg_str = f"{day_chg:+.1f}%" if day_chg is not None else "N/A"
        row = [
            str(rank),
            r.get("ticker", ""),
            (r.get("company_name") or "")[:18],
            f"${_fmt(r.get('price'), 2)}",
            chg_str,
            _fmt(r.get("rel_volume"), 1),
            _fmt_currency(r.get("market_cap")),
            str(r.get("kat_score", 0)),
            grade,
            (r.get("setup_type") or "")[:18],
            action[:12],
            conf,
            (r.get("strongest_reason") or "")[:26],
            (r.get("biggest_risk") or "")[:22],
        ]
        print("  ".join(str(v).ljust(w) for v, w in zip(row, widths)))


def save_csv(results: list[dict], path: str):
    if not results:
        logger.warning("No results to save to CSV.")
        return
    try:
        rows = []
        for r in results:
            row = {k: v for k, v in r.items() if k != "price_history"}
            if isinstance(row.get("news_headlines"), list):
                row["news_headlines"] = " | ".join(row["news_headlines"])
            rows.append(row)
        df = pd.DataFrame(rows)
        df.to_csv(path, index=False)
        logger.info(f"Results saved to {path}")
        print(f"\n  Saved CSV: {path}")
    except Exception as e:
        logger.error(f"Failed to save CSV: {e}")


def save_json(results: list[dict], path: str, meta: dict | None = None):
    if not results:
        logger.warning("No results to save to JSON.")
        return
    try:
        output = {"meta": meta or {}, "results": []}
        for r in results:
            row = {k: v for k, v in r.items() if k != "price_history"}
            if isinstance(row.get("news_headlines"), list):
                row["news_headlines"] = row["news_headlines"]
            output["results"].append(row)

        with open(path, "w") as f:
            json.dump(output, f, indent=2, default=str)
        logger.info(f"Results saved to {path}")
        print(f"  Saved JSON: {path}")
    except Exception as e:
        logger.error(f"Failed to save JSON: {e}")


def print_failure_summary(failed_tickers: list[str]):
    if not failed_tickers:
        return
    n = len(failed_tickers)
    examples = ", ".join(failed_tickers[:10])
    more = f" ... and {n-10} more" if n > 10 else ""
    print(f"\n  [Warning] {n} ticker(s) failed to fetch: {examples}{more}")
