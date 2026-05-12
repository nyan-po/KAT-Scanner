"""
KAT Market Screener — Streamlit Web Interface
Run with:  streamlit run app.py
"""
import sys
import os
import time
import json
import pandas as pd
from datetime import datetime

import streamlit as st

sys.path.insert(0, os.path.dirname(__file__))

from src.config import (
    load_config, get_filters, get_universe_config,
    get_watchlist, get_sector_mappings,
)
from src.universe import (
    build_universe, build_watchlist_universe,
    build_manual_universe, build_csv_universe,
)
from src.data import fetch_ticker_data
from src.scoring import score_short_term, score_long_term
from src.grading import score_to_grade
from src.filters import apply_filters, sort_results, limit_results

# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="KAT Market Screener",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Colour maps ────────────────────────────────────────────────────────────────
GRADE_BG = {
    "A+": "#00c853", "A": "#2e7d32", "A-": "#388e3c",
    "B+": "#0277bd", "B": "#0288d1", "B-": "#f57f17",
    "C":  "#e65100", "D": "#b71c1c",
}

# ── Helpers ────────────────────────────────────────────────────────────────────
def fmt_cap(v):
    if v is None:
        return "N/A"
    v = float(v)
    if v >= 1e12:
        return f"${v/1e12:.2f}T"
    if v >= 1e9:
        return f"${v/1e9:.2f}B"
    if v >= 1e6:
        return f"${v/1e6:.2f}M"
    return f"${v:.0f}"


def fmt_pct(v, decimals=1):
    if v is None:
        return "N/A"
    return f"{float(v):+.{decimals}f}%"


def grade_color_style(val):
    bg = GRADE_BG.get(val, "#555")
    return f"background-color:{bg};color:white;font-weight:bold;text-align:center;border-radius:4px"


def action_color_style(val):
    v = (val or "").lower()
    if "buy" in v:
        return "color:#00c853;font-weight:bold"
    if "wait" in v:
        return "color:#f9a825;font-weight:bold"
    if "watchlist" in v:
        return "color:#29b6f6"
    if "avoid" in v:
        return "color:#ef5350;font-weight:bold"
    return ""


def chg_color_style(val):
    if not val or val == "N/A":
        return ""
    try:
        v = float(str(val).replace("%", "").replace("+", ""))
        if v > 0:
            return "color:#00c853;font-weight:bold"
        if v < 0:
            return "color:#ef5350"
    except Exception:
        pass
    return ""


# ── Config ─────────────────────────────────────────────────────────────────────
@st.cache_resource
def _load_cfg():
    return load_config()

cfg = _load_cfg()

# ── Session state ──────────────────────────────────────────────────────────────
for key, default in [
    ("results", []),
    ("scan_meta", {}),
    ("selected_idx", None),
]:
    if key not in st.session_state:
        st.session_state[key] = default


# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 📈 KAT Screener")
    st.divider()

    st.markdown("### Scan")
    scan_type = st.selectbox(
        "Scan type",
        ["watchlist", "market", "manual"],
        help="Market scan: ~500 tickers, takes 5-10 min",
    )
    mode = st.selectbox(
        "Mode",
        ["short_term", "long_term"],
        format_func=lambda x: "📊 Short Term" if x == "short_term" else "📐 Long Term",
    )

    manual_input = ""
    if scan_type == "manual":
        manual_input = st.text_area(
            "Tickers",
            placeholder="NVDA\nAMD\nTSLA  (one per line or comma-separated)",
            height=100,
        )

    if scan_type == "market":
        st.info("Market scan fetches ~500 tickers. Expect 5-10 minutes.")

    st.divider()
    st.markdown("### Filters")

    min_grade = st.selectbox(
        "Min KAT grade",
        [None, "A+", "A", "A-", "B+", "B", "B-", "C"],
        format_func=lambda x: "— no filter —" if x is None else x,
    )
    min_rel_vol_raw = st.number_input(
        "Min relative volume", min_value=0.0, max_value=10.0,
        value=0.0, step=0.1,
        help="0 = no filter",
    )
    min_rel_vol = min_rel_vol_raw if min_rel_vol_raw > 0 else None

    min_cap = st.selectbox(
        "Min market cap",
        [None, 50_000_000, 200_000_000, 1_000_000_000, 5_000_000_000, 10_000_000_000],
        format_func=lambda x: "— no filter —" if x is None else (
            f"${x/1e9:.0f}B" if x >= 1e9 else f"${x/1e6:.0f}M"
        ),
    )
    max_results = st.slider("Max results", 10, 200, 50, step=10)

    c1, c2 = st.columns(2)
    with c1:
        excl_etfs = st.toggle("No ETFs", value=False)
    with c2:
        excl_low = st.toggle("No <$5", value=False)

    st.divider()
    run_btn = st.button("🚀  Run Scan", type="primary", use_container_width=True)

    # Download — only when results exist
    if st.session_state.results:
        st.divider()
        dl_rows = [
            {k: ("|".join(v) if isinstance(v, list) else v)
             for k, v in r.items() if k != "price_history"}
            for r in st.session_state.results
        ]
        st.download_button(
            "⬇ Download CSV",
            pd.DataFrame(dl_rows).to_csv(index=False),
            file_name=f"kat_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
            mime="text/csv",
            use_container_width=True,
        )
        meta_json = {
            "meta": st.session_state.scan_meta,
            "results": dl_rows,
        }
        st.download_button(
            "⬇ Download JSON",
            json.dumps(meta_json, indent=2, default=str),
            file_name=f"kat_{datetime.now().strftime('%Y%m%d_%H%M')}.json",
            mime="application/json",
            use_container_width=True,
        )


# ── Scan execution ─────────────────────────────────────────────────────────────
if run_btn:
    st.session_state.results = []
    st.session_state.selected_idx = None

    watchlist = get_watchlist(cfg)
    sector_mappings = get_sector_mappings(cfg)
    score_fn = score_short_term if mode == "short_term" else score_long_term

    # Build ticker list
    with st.spinner("Building universe..."):
        if scan_type == "watchlist":
            tickers = build_watchlist_universe(watchlist)
        elif scan_type == "manual":
            raw = manual_input.replace(",", "\n").split()
            tickers = build_manual_universe([t.strip() for t in raw if t.strip()])
        else:
            tickers = build_universe(get_universe_config(cfg), watchlist)

    if not tickers:
        st.error("No tickers to scan. Check your input or watchlist in config.yaml.")
        st.stop()

    total = len(tickers)
    progress = st.progress(0.0, text=f"Scanning 0 / {total}…")
    status = st.empty()
    results_raw = []
    failed = []

    for i, ticker in enumerate(tickers, 1):
        pct = i / total
        progress.progress(pct, text=f"Scanning {i} / {total} — {ticker}")

        data = fetch_ticker_data(ticker)
        if data:
            try:
                kat_sector = next(
                    (s for s, members in sector_mappings.items() if ticker in members),
                    None,
                )
                scores = score_fn(data, kat_sector=kat_sector)
                grade = score_to_grade(scores["kat_score"])
                results_raw.append({**data, **scores, "kat_grade": grade})
            except Exception:
                failed.append(ticker)
        else:
            failed.append(ticker)

        time.sleep(0.05)

    progress.empty()
    status.empty()

    # Apply filters
    f_overrides = {
        "max_results": max_results,
        **({"min_grade": min_grade} if min_grade else {}),
        **({"min_relative_volume": min_rel_vol} if min_rel_vol else {}),
        **({"min_market_cap": min_cap} if min_cap else {}),
        **({"exclude_etfs": True} if excl_etfs else {}),
        **({"exclude_low_priced": True} if excl_low else {}),
    }
    filters = get_filters(cfg, f_overrides)
    filtered = apply_filters(results_raw, filters)
    final = limit_results(sort_results(filtered), max_results)

    st.session_state.results = final
    st.session_state.scan_meta = {
        "scan_type": scan_type,
        "mode": mode,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "tickers_scanned": total,
        "tickers_passed": len(final),
        "failed": failed,
    }
    st.rerun()


# ── Main view ──────────────────────────────────────────────────────────────────
st.markdown("# 📈 KAT Market Screener")

if not st.session_state.results:
    st.markdown("""
    **Market-wide stock screener using the KAT grading model (A+ → D).**

    #### Quick start
    1. Choose **Scan type** and **Mode** in the sidebar
    2. Set any filters you want
    3. Hit **🚀 Run Scan**

    | Scan type | Speed | Description |
    |-----------|-------|-------------|
    | `watchlist` | ~10s | Tickers from your config watchlist |
    | `market` | 5-10 min | Full S&P 500 + Nasdaq 100 universe |
    | `manual` | ~Ns | Any tickers you enter |

    | Mode | Focus |
    |------|-------|
    | `short_term` | Volume, momentum, catalysts, technicals |
    | `long_term` | Revenue growth, balance sheet, FCF, valuation |
    """)
    st.info("👈 Configure and run a scan in the sidebar to see results.")
    st.stop()

# ── Scan summary ───────────────────────────────────────────────────────────────
meta = st.session_state.scan_meta
results = st.session_state.results

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Scan", meta.get("scan_type", "—").title())
c2.metric("Mode", "Short Term" if meta.get("mode") == "short_term" else "Long Term")
c3.metric("Scanned", meta.get("tickers_scanned", 0))
c4.metric("Showing", meta.get("tickers_passed", 0))
c5.metric("Timestamp", meta.get("timestamp", "—")[-8:])  # show HH:MM:SS

if meta.get("failed"):
    with st.expander(f"⚠️ {len(meta['failed'])} tickers failed to fetch", expanded=False):
        st.write(", ".join(meta["failed"]))

st.divider()

# ── Results table ──────────────────────────────────────────────────────────────
rows = []
for i, r in enumerate(results, 1):
    price = r.get("price")
    chg = r.get("day_change_pct")
    rv = r.get("rel_volume")
    rows.append({
        "Rank":    i,
        "Ticker":  r.get("ticker", ""),
        "Company": (r.get("company_name") or "")[:28],
        "Price":   f"${price:.2f}" if price else "N/A",
        "% Chg":   fmt_pct(chg),
        "RelVol":  f"{rv:.1f}x" if rv is not None else "N/A",
        "Mkt Cap": fmt_cap(r.get("market_cap")),
        "Score":   r.get("kat_score", 0),
        "Grade":   r.get("kat_grade", "D"),
        "Setup":   r.get("setup_type", ""),
        "Action":  r.get("suggested_action", ""),
        "Conf":    r.get("confidence", ""),
        "Strongest Reason": (r.get("strongest_reason") or "")[:45],
        "Biggest Risk":     (r.get("biggest_risk") or "")[:40],
    })

df = pd.DataFrame(rows)

styled = (
    df.style
    .map(grade_color_style,  subset=["Grade"])
    .map(action_color_style, subset=["Action"])
    .map(chg_color_style,    subset=["% Chg"])
    .set_properties(subset=["Rank", "Score"], **{"text-align": "center"})
)

event = st.dataframe(
    styled,
    use_container_width=True,
    hide_index=True,
    on_select="rerun",
    selection_mode="single-row",
    height=min(700, 60 + len(rows) * 36),
    key="results_table",
)

# Handle row selection
sel_rows = (event.selection or {}).get("rows", [])
if sel_rows:
    st.session_state.selected_idx = sel_rows[0]


# ── Ticker detail panel ────────────────────────────────────────────────────────
def _render_detail(r: dict):
    ticker  = r.get("ticker", "")
    company = r.get("company_name", ticker)
    price   = r.get("price")
    chg     = r.get("day_change_pct")
    grade   = r.get("kat_grade", "D")
    score   = r.get("kat_score", 0)
    mode_r  = r.get("mode", "short_term")

    # ── Header ─────────────────────────────────────────────────────────────────
    grade_bg = GRADE_BG.get(grade, "#555")
    chg_color = "#00c853" if (chg or 0) > 0 else "#ef5350"
    chg_str = fmt_pct(chg)

    st.markdown(
        f"""
        <div style="display:flex;align-items:center;gap:16px;margin-bottom:8px">
          <span style="font-size:2rem;font-weight:900">{ticker}</span>
          <span style="font-size:1.1rem;color:#aaa">{company}</span>
          <span style="font-size:1.5rem;font-weight:bold">${price:.2f}</span>
          <span style="font-size:1.2rem;color:{chg_color};font-weight:bold">{chg_str}</span>
          <span style="background:{grade_bg};color:white;padding:4px 14px;
                       border-radius:6px;font-size:1.4rem;font-weight:900">{grade}</span>
          <span style="font-size:1rem;color:#aaa">Score: {score}/100</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    sector   = r.get("sector", "N/A")
    industry = r.get("industry", "N/A")
    st.caption(f"**{sector}** · {industry}  |  Mode: {mode_r.replace('_',' ').title()}")

    st.divider()

    # ── Key metrics ─────────────────────────────────────────────────────────────
    col1, col2, col3, col4, col5, col6 = st.columns(6)
    col1.metric("Market Cap",    fmt_cap(r.get("market_cap")))
    col2.metric("Rel Volume",    f"{r.get('rel_volume'):.1f}x" if r.get("rel_volume") else "N/A")
    col3.metric("Avg Volume",    fmt_cap(r.get("avg_volume")))
    col4.metric("52W High",      f"${r.get('week52_high'):.2f}" if r.get("week52_high") else "N/A")
    col5.metric("Dist 52W High", fmt_pct(r.get("dist_from_52w_high_pct")))
    col6.metric("Earnings Date", r.get("earnings_date") or "N/A")

    st.divider()

    # ── Signal columns ──────────────────────────────────────────────────────────
    left, mid, right = st.columns(3)

    with left:
        st.markdown("#### 📡 Technical")
        signal = r.get("technical_signal", "N/A")
        signal_color = (
            "#00c853" if "bullish" in signal else
            "#ef5350" if "bearish" in signal or "avoid" in signal else
            "#f9a825"
        )
        st.markdown(
            f'<span style="color:{signal_color};font-weight:bold">{signal}</span>',
            unsafe_allow_html=True,
        )
        st.caption(r.get("technical_notes") or "No technical notes")
        st.markdown(f"**9 EMA:** {r.get('ema9') or 'N/A'}  |  **20 EMA:** {r.get('ema20') or 'N/A'}")
        st.markdown(f"**50 SMA:** {r.get('sma50') or 'N/A'}  |  **200 SMA:** {r.get('sma200') or 'N/A'}")
        st.markdown(f"**5d return:** {fmt_pct(r.get('return_5d'))}  |  **20d:** {fmt_pct(r.get('return_20d'))}")
        if r.get("is_extended"):
            st.warning("⚠️ Extended above 9 EMA")

    with mid:
        st.markdown("#### 📊 Fundamentals")
        fund_signal = r.get("fundamental_signal", "neutral")
        fund_color = (
            "#00c853" if fund_signal in ("strong", "positive") else
            "#ef5350" if fund_signal in ("weak", "poor") else
            "#aaa"
        )
        st.markdown(
            f'<span style="color:{fund_color};font-weight:bold">{fund_signal}</span>',
            unsafe_allow_html=True,
        )
        st.markdown(f"**Revenue growth:** {fmt_pct(r.get('revenue_growth'))}")
        st.markdown(f"**Earnings growth:** {fmt_pct(r.get('earnings_growth'))}")
        st.markdown(f"**Gross margin:** {fmt_pct(r.get('gross_margin'))}")
        st.markdown(f"**Op margin:** {fmt_pct(r.get('operating_margin'))}")
        st.markdown(f"**PE:** {r.get('pe') or 'N/A'}  |  **Fwd PE:** {r.get('forward_pe') or 'N/A'}")
        st.markdown(f"**P/S:** {r.get('ps_ratio') or 'N/A'}")
        st.markdown(f"**FCF:** {fmt_cap(r.get('free_cash_flow'))}")
        val_sig = r.get("valuation_signal", "")
        if val_sig:
            st.caption(f"Valuation: {val_sig}")

    with right:
        st.markdown("#### 📰 Catalyst & Risk")
        cat_quality = r.get("catalyst_quality", "none")
        cat_color = (
            "#00c853" if "positive" in cat_quality else
            "#ef5350" if "negative" in cat_quality else
            "#aaa"
        )
        st.markdown(
            f'<span style="color:{cat_color};font-weight:bold">{cat_quality}</span>',
            unsafe_allow_html=True,
        )
        st.markdown(f"**Summary:** {r.get('catalyst_summary') or 'No recent news'}")
        st.markdown(f"**Volume signal:** {r.get('volume_signal') or 'N/A'}")
        if r.get("dilution_flag"):
            st.error("⚠️ Dilution / offering risk detected")
        short_pct = r.get("short_percent_float")
        if short_pct:
            st.markdown(f"**Short float:** {short_pct:.1f}%")

        # News headlines
        headlines = r.get("news_headlines") or []
        if headlines:
            with st.expander("Recent headlines"):
                for h in headlines:
                    st.markdown(f"- {h}")

    st.divider()

    # ── Action recommendation ───────────────────────────────────────────────────
    action = r.get("suggested_action", "avoid")
    action_bg = {
        "buy": "#1b5e20", "accumulate": "#1b5e20",
        "wait": "#4e342e",
        "watchlist": "#0d47a1",
        "avoid": "#7f0000",
    }
    bg = next((v for k, v in action_bg.items() if k in action.lower()), "#333")

    st.markdown(
        f"""
        <div style="background:{bg};border-radius:8px;padding:12px 20px;margin-bottom:8px">
          <span style="font-size:1rem;color:#ddd">Suggested Action</span><br>
          <span style="font-size:1.4rem;font-weight:900;color:white">{action.upper()}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    a1, a2, a3 = st.columns(3)
    a1.markdown(f"**Setup:** {r.get('setup_type', 'N/A')}")
    a2.markdown(f"**Confidence:** {r.get('confidence', 'N/A')}")
    a3.markdown(f"**Invalidation:** {r.get('invalidation') or 'N/A'}")

    st.markdown(f"✅ **Strongest reason:** {r.get('strongest_reason') or 'N/A'}")
    st.markdown(f"⚠️ **Biggest risk:** {r.get('biggest_risk') or 'N/A'}")

    # ── Score breakdown ─────────────────────────────────────────────────────────
    st.divider()
    st.markdown("#### Score Breakdown")

    if mode_r == "short_term":
        components = [
            ("Catalyst / News",     r.get("score_catalyst", 0),     20),
            ("Relative Volume",     r.get("score_volume", 0),        20),
            ("Technical Setup",     r.get("score_technical", 0),     20),
            ("Earnings Timing",     r.get("score_earnings", 0),      15),
            ("Sector Tailwind",     r.get("score_sector", 0),        10),
            ("Short Interest",      r.get("score_short_interest", 0), 5),
            ("Risk Penalty",       -r.get("score_risk_penalty", 0),   5),
        ]
    else:
        components = [
            ("Revenue Growth",     r.get("score_revenue", 0),        20),
            ("Earnings Trend",     r.get("score_earnings_lt", 0),    15),
            ("Balance Sheet",      r.get("score_balance_sheet", 0),  15),
            ("FCF Trend",          r.get("score_fcf", 0),            15),
            ("Valuation",          r.get("score_valuation", 0),      10),
            ("Sector Tailwind",    r.get("score_sector", 0),         10),
            ("Execution Proxy",    r.get("score_execution", 0),      10),
            ("Dilution Penalty",  -r.get("score_dilution_penalty", 0), 5),
        ]

    for label, val, mx in components:
        display_val = max(0, val)
        pct = display_val / mx if mx else 0
        color = "#ef5350" if val < 0 else ("#00c853" if pct >= 0.7 else "#0288d1" if pct >= 0.4 else "#f9a825")
        st.markdown(
            f"""
            <div style="display:flex;align-items:center;gap:10px;margin:4px 0">
              <span style="width:160px;font-size:0.85rem;color:#ccc">{label}</span>
              <div style="flex:1;background:#333;border-radius:4px;height:14px">
                <div style="width:{min(100,pct*100):.0f}%;background:{color};height:14px;border-radius:4px"></div>
              </div>
              <span style="width:60px;text-align:right;font-size:0.85rem;color:#eee">{val:+d} / {mx}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )


if st.session_state.selected_idx is not None:
    idx = st.session_state.selected_idx
    if 0 <= idx < len(results):
        st.divider()
        st.markdown(f"### 🔍 Ticker Detail — click another row to switch")
        _render_detail(results[idx])
else:
    st.caption("👆 Click any row in the table to see full ticker detail.")
