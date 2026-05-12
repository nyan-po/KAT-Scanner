"""
KAT Market Screener — Streamlit web UI.
Run with:  streamlit run app.py
"""
import os
import sys
import logging
from datetime import datetime

import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.dirname(__file__))

from src.config import (
    load_config, get_filters, get_universe_config,
    get_watchlist, get_sector_mappings,
)
from src.universe import (
    build_universe, build_watchlist_universe, build_manual_universe,
)
from src.data import fetch_batch
from src.scoring import score_short_term, score_long_term
from src.grading import score_to_grade, GRADE_ORDER
from src.filters import apply_filters, sort_results
from src.alerts import (
    add_alert, remove_alert, reset_alert, check_alerts,
    CONDITION_LABELS,
)
from src.discord_notify import send_alert, send_batch, send_test
from src.scenario_gen import generate_scenarios

try:
    cfg = load_config()
except Exception:
    cfg = {}

logging.basicConfig(level=logging.WARNING)

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="KAT Market Screener",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Session state initialisation
# ---------------------------------------------------------------------------
if "results" not in st.session_state:
    st.session_state.results = []
if "alerts" not in st.session_state:
    st.session_state.alerts = []
if "discord_webhook" not in st.session_state:
    st.session_state.discord_webhook = os.getenv("DISCORD_WEBHOOK_URL", "")
if "selected_ticker" not in st.session_state:
    st.session_state.selected_ticker = None
if "last_scan_meta" not in st.session_state:
    st.session_state.last_scan_meta = None

# ---------------------------------------------------------------------------
# Grade color helpers
# ---------------------------------------------------------------------------
_GRADE_COLORS = {
    "A+": "#00e676", "A": "#69f0ae", "A-": "#b9f6ca",
    "B+": "#40c4ff", "B":  "#80d8ff", "B-": "#ffe57f",
    "C":  "#ffab40", "D":  "#ff5252",
}

def _grade_badge(grade: str) -> str:
    color = _GRADE_COLORS.get(grade, "#888888")
    return f'<span style="background:{color};color:#000;padding:2px 8px;border-radius:4px;font-weight:700">{grade}</span>'

def _action_color(action: str) -> str:
    a = action.lower()
    if "buy" in a:   return "green"
    if "wait" in a:  return "orange"
    if "watch" in a: return "blue"
    return "red"

# ---------------------------------------------------------------------------
# Sidebar — scan configuration
# ---------------------------------------------------------------------------
with st.sidebar:
    st.title("📈 KAT Scanner")
    st.markdown("---")

    scan_type = st.selectbox("Scan type", ["market", "watchlist", "tickers"])
    mode = st.selectbox("Analysis mode", ["short_term", "long_term"],
                        format_func=lambda x: x.replace("_", " ").title())

    manual_input = ""
    if scan_type == "tickers":
        manual_input = st.text_input("Tickers (comma-separated)", placeholder="NVDA, AAPL, MSFT")

    st.markdown("**Filters**")
    min_grade = st.selectbox("Min grade", ["(none)"] + GRADE_ORDER)
    min_score = st.number_input("Min score", 0, 100, 0, step=5)
    min_rel_vol = st.number_input("Min rel volume", 0.0, 20.0, 0.0, step=0.5)
    max_results = st.number_input("Max results", 1, 500, 50, step=10)
    exclude_etfs = st.checkbox("Exclude ETFs", value=True)

    st.markdown("---")
    run_scan = st.button("🔍 Run Scan", use_container_width=True, type="primary")

# ---------------------------------------------------------------------------
# Scan execution
# ---------------------------------------------------------------------------
if run_scan:
    tickers: list[str] = []
    universe_cfg = get_universe_config(cfg)
    watchlist = get_watchlist(cfg)
    sector_mappings = get_sector_mappings(cfg)

    with st.spinner("Building universe…"):
        try:
            if scan_type == "tickers" and manual_input.strip():
                tickers = build_manual_universe(
                    [t.strip().upper() for t in manual_input.split(",") if t.strip()]
                )
            elif scan_type == "watchlist":
                tickers = build_watchlist_universe(watchlist)
            else:
                tickers = build_universe(universe_cfg, watchlist)
        except Exception as e:
            st.error(f"Failed to build universe: {e}")

    if tickers:
        with st.spinner(f"Fetching data for {len(tickers)} tickers…"):
            raw_data = fetch_batch(tickers, show_progress=False)

        score_fn = score_short_term if mode == "short_term" else score_long_term
        results_raw = []
        with st.spinner("Scoring…"):
            for ticker, data in raw_data.items():
                try:
                    kat_sector = next(
                        (s for s, members in sector_mappings.items() if ticker in members),
                        None,
                    )
                    scores = score_fn(data, kat_sector=kat_sector)
                    grade = score_to_grade(scores["kat_score"])
                    results_raw.append({**data, **scores, "kat_grade": grade})
                except Exception:
                    pass

        # Build filter overrides
        overrides: dict = {}
        if min_grade != "(none)":
            overrides["min_grade"] = min_grade
        if min_score > 0:
            overrides["min_grade"] = min_grade if min_grade != "(none)" else None
        if min_rel_vol > 0:
            overrides["min_relative_volume"] = min_rel_vol
        if exclude_etfs:
            overrides["exclude_etfs"] = True

        filters = get_filters(cfg, overrides)
        if min_score > 0:
            results_raw = [r for r in results_raw if r.get("kat_score", 0) >= min_score]

        filtered = apply_filters(results_raw, filters)
        final = sort_results(filtered, key="kat_score", ascending=False)
        if max_results:
            final = final[:int(max_results)]

        st.session_state.results = final
        st.session_state.last_scan_meta = {
            "scan_type": scan_type,
            "mode": mode,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "scanned": len(tickers),
            "passed": len(final),
        }
        st.success(f"Scan complete — {len(final)} results from {len(tickers)} tickers.")

# ---------------------------------------------------------------------------
# Main tabs
# ---------------------------------------------------------------------------
tab_results, tab_detail, tab_alerts, tab_settings = st.tabs(
    ["📊 Results", "🔬 Detail", "🔔 Alerts", "⚙️ Settings"]
)

# ── Results tab ──────────────────────────────────────────────────────────────
with tab_results:
    meta = st.session_state.last_scan_meta
    if meta:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Scan type", meta["scan_type"])
        c2.metric("Mode", meta["mode"].replace("_", " ").title())
        c3.metric("Tickers scanned", meta["scanned"])
        c4.metric("Passed filters", meta["passed"])
        st.caption(f"Last scan: {meta['timestamp']}")

    results = st.session_state.results
    if not results:
        st.info("Run a scan from the sidebar to see results here.")
    else:
        rows = []
        for r in results:
            day_chg = r.get("day_change_pct")
            rows.append({
                "Ticker":    r.get("ticker", ""),
                "Company":   (r.get("company_name") or "")[:28],
                "Price":     r.get("price"),
                "% Chg":     day_chg,
                "Rel Vol":   r.get("rel_volume"),
                "Mkt Cap":   r.get("market_cap"),
                "Score":     r.get("kat_score", 0),
                "Grade":     r.get("kat_grade", "D"),
                "Setup":     r.get("setup_type", ""),
                "Action":    r.get("suggested_action", ""),
                "Conf":      r.get("confidence", ""),
            })
        df = pd.DataFrame(rows)

        # Format numeric columns
        def _fmt_price(v):
            return f"${v:.2f}" if v is not None else "N/A"

        def _fmt_pct(v):
            return f"{v:+.1f}%" if v is not None else "N/A"

        def _fmt_mktcap(v):
            if v is None: return "N/A"
            if v >= 1e12: return f"${v/1e12:.1f}T"
            if v >= 1e9:  return f"${v/1e9:.1f}B"
            if v >= 1e6:  return f"${v/1e6:.1f}M"
            return f"${v:,.0f}"

        display = df.copy()
        display["Price"]   = display["Price"].apply(_fmt_price)
        display["% Chg"]   = display["% Chg"].apply(_fmt_pct)
        display["Rel Vol"] = display["Rel Vol"].apply(
            lambda v: f"{v:.1f}x" if v is not None else "N/A"
        )
        display["Mkt Cap"] = display["Mkt Cap"].apply(_fmt_mktcap)

        st.dataframe(
            display,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Score": st.column_config.ProgressColumn(
                    "Score", min_value=0, max_value=100, format="%d"
                ),
            },
        )

        # Ticker selector for detail tab
        tickers_in_results = [r.get("ticker", "") for r in results]
        selected = st.selectbox(
            "Select ticker for detail view →",
            ["(select)"] + tickers_in_results,
            key="result_ticker_select",
        )
        if selected != "(select)":
            st.session_state.selected_ticker = selected

        # CSV download
        csv_data = display.to_csv(index=False)
        st.download_button(
            "⬇ Download CSV",
            data=csv_data,
            file_name=f"kat_scan_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
            mime="text/csv",
        )

# ── Detail tab ────────────────────────────────────────────────────────────────
with tab_detail:
    ticker_sel = st.session_state.selected_ticker
    results = st.session_state.results

    if not ticker_sel or not results:
        st.info("Select a ticker from the Results tab, or run a single-ticker scan.")
        # Allow manual fetch
        manual_ticker = st.text_input("Or enter a ticker to analyse", placeholder="NVDA")
        detail_mode = st.selectbox("Mode", ["short_term", "long_term"],
                                   format_func=lambda x: x.replace("_", " ").title(),
                                   key="detail_mode")
        if st.button("Analyse") and manual_ticker.strip():
            with st.spinner(f"Fetching {manual_ticker.upper()}…"):
                raw = fetch_batch([manual_ticker.upper().strip()], show_progress=False)
            if raw:
                data = list(raw.values())[0]
                score_fn = score_short_term if detail_mode == "short_term" else score_long_term
                scores = score_fn(data)
                grade = score_to_grade(scores["kat_score"])
                result = {**data, **scores, "kat_grade": grade}
                st.session_state.results = [result]
                st.session_state.selected_ticker = manual_ticker.upper().strip()
                st.rerun()
            else:
                st.error(f"Could not fetch data for {manual_ticker.upper()}.")
    else:
        data = next((r for r in results if r.get("ticker") == ticker_sel), None)
        if data is None:
            st.warning(f"No data found for {ticker_sel}.")
        else:
            st.subheader(f"{ticker_sel} — {data.get('company_name', '')}")

            # Header metrics
            price = data.get("price")
            day_chg = data.get("day_change_pct")
            score = data.get("kat_score", 0)
            grade = data.get("kat_grade", "D")

            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Price", f"${price:.2f}" if price else "N/A",
                        f"{day_chg:+.1f}%" if day_chg is not None else None)
            col2.metric("KAT Score", score)
            col3.metric("KAT Grade", grade)
            col4.metric("Action", data.get("suggested_action", "N/A"))

            st.markdown("---")

            # Score breakdown
            with st.expander("Score breakdown", expanded=True):
                mode_val = data.get("mode", "short_term")
                if mode_val == "short_term":
                    components = {
                        "Catalyst":      data.get("score_catalyst", 0),
                        "Volume":        data.get("score_volume", 0),
                        "Technical":     data.get("score_technical", 0),
                        "Earnings":      data.get("score_earnings", 0),
                        "Sector":        data.get("score_sector", 0),
                        "Short interest":data.get("score_short_interest", 0),
                        "Risk penalty":  -data.get("score_risk_penalty", 0),
                    }
                else:
                    components = {
                        "Revenue growth":  data.get("score_revenue", 0),
                        "Earnings trend":  data.get("score_earnings_lt", 0),
                        "Balance sheet":   data.get("score_balance_sheet", 0),
                        "Free cash flow":  data.get("score_fcf", 0),
                        "Valuation":       data.get("score_valuation", 0),
                        "Sector":          data.get("score_sector", 0),
                        "Execution":       data.get("score_execution", 0),
                        "Dilution penalty":-data.get("score_dilution_penalty", 0),
                    }
                comp_df = pd.DataFrame(
                    {"Component": list(components.keys()), "Points": list(components.values())}
                )
                st.bar_chart(comp_df.set_index("Component"))

            col_l, col_r = st.columns(2)
            with col_l:
                st.markdown("**Signals**")
                st.write(f"**Technical:** {data.get('technical_signal', 'N/A')}")
                st.write(f"**Fundamental:** {data.get('fundamental_signal', 'N/A')}")
                st.write(f"**Valuation:** {data.get('valuation_signal', 'N/A')}")
                st.write(f"**Volume:** {data.get('volume_signal', 'N/A')}")
                st.write(f"**Setup:** {data.get('setup_type', 'N/A')}")
                st.write(f"**Confidence:** {data.get('confidence', 'N/A')}")

            with col_r:
                st.markdown("**Catalyst**")
                st.write(data.get("catalyst_summary", "No recent news."))
                st.markdown("**Strongest reason**")
                st.write(data.get("strongest_reason", "N/A"))
                st.markdown("**Biggest risk**")
                st.write(data.get("biggest_risk", "N/A"))
                if data.get("invalidation"):
                    st.markdown("**Invalidation**")
                    st.write(data["invalidation"])

            # Scenarios
            st.markdown("---")
            st.subheader("Scenarios")
            scenarios = generate_scenarios(data)
            s_cols = st.columns(3)
            colors = {"Bull": "🟢", "Base": "🟡", "Bear": "🔴"}
            for col, s in zip(s_cols, scenarios):
                with col:
                    icon = colors.get(s["scenario"], "")
                    st.markdown(f"#### {icon} {s['scenario']}")
                    st.metric("Return", s["return_pct"], delta_color="normal")
                    st.write(f"**Target:** {s['target_price']}")
                    st.write(f"**Probability:** {s['probability']}")
                    st.write(f"**Horizon:** {s['time_horizon']}")
                    st.caption(s["description"])
                    st.caption(f"Key driver: {s['key_driver']}")

# ── Alerts tab ────────────────────────────────────────────────────────────────
with tab_alerts:
    st.subheader("Alert Rules")

    with st.form("add_alert_form", clear_on_submit=True):
        ac1, ac2, ac3 = st.columns([2, 3, 2])
        new_ticker = ac1.text_input("Ticker", placeholder="NVDA").upper().strip()
        new_condition = ac2.selectbox(
            "Condition",
            list(CONDITION_LABELS.keys()),
            format_func=lambda k: CONDITION_LABELS[k],
        )
        # Use grade list for grade conditions, float otherwise
        if new_condition == "grade_gte":
            new_threshold = ac3.selectbox("Grade", GRADE_ORDER)
        else:
            new_threshold = ac3.number_input("Value", value=70.0, step=1.0)

        submitted = st.form_submit_button("➕ Add Alert")
        if submitted and new_ticker:
            alert = add_alert(new_ticker, new_condition, new_threshold)
            st.session_state.alerts.append(alert)
            st.success(f"Alert added for {new_ticker}.")

    # Display existing alerts
    alerts = st.session_state.alerts
    if not alerts:
        st.info("No alerts configured yet.")
    else:
        for alert in alerts:
            cond_label = CONDITION_LABELS.get(alert["condition"], alert["condition"])
            status = "✅ Triggered" if alert["triggered"] else "⏳ Watching"
            with st.container():
                rc1, rc2, rc3, rc4 = st.columns([2, 4, 2, 2])
                rc1.markdown(f"**{alert['ticker']}**")
                rc2.write(f"{cond_label} {alert['threshold']}")
                rc3.write(status)
                btn_col1, btn_col2 = rc4.columns(2)
                if btn_col1.button("↺", key=f"reset_{alert['id']}", help="Reset"):
                    st.session_state.alerts = reset_alert(
                        st.session_state.alerts, alert["id"]
                    )
                    st.rerun()
                if btn_col2.button("✕", key=f"del_{alert['id']}", help="Delete"):
                    st.session_state.alerts = remove_alert(
                        st.session_state.alerts, alert["id"]
                    )
                    st.rerun()
        st.markdown("---")

    # Check alerts against last scan
    results = st.session_state.results
    if results and alerts:
        if st.button("🔔 Check Alerts Against Last Scan"):
            triggered = check_alerts(st.session_state.alerts, results)
            if triggered:
                st.warning(f"{len(triggered)} alert(s) triggered!")
                for t in triggered:
                    r = t.get("result", {})
                    st.write(
                        f"**{t['ticker']}** — {CONDITION_LABELS.get(t['condition'], t['condition'])} "
                        f"{t['threshold']} (Score: {r.get('kat_score')}, Grade: {r.get('kat_grade')})"
                    )
                webhook = st.session_state.discord_webhook
                if webhook:
                    if send_batch(triggered, webhook):
                        st.success("Discord notification sent.")
                    else:
                        st.error("Discord notification failed.")
                else:
                    st.info("Configure a Discord webhook in Settings to receive notifications.")
            else:
                st.success("No alerts triggered.")
    elif not results:
        st.info("Run a scan first to check alerts against results.")

# ── Settings tab ─────────────────────────────────────────────────────────────
with tab_settings:
    st.subheader("Discord Notifications")

    webhook = st.text_input(
        "Discord Webhook URL",
        value=st.session_state.discord_webhook,
        type="password",
        placeholder="https://discord.com/api/webhooks/…",
    )
    if webhook != st.session_state.discord_webhook:
        st.session_state.discord_webhook = webhook

    col_test, _ = st.columns([1, 3])
    if col_test.button("📨 Send Test Notification"):
        if not webhook:
            st.error("Enter a webhook URL first.")
        elif send_test(webhook):
            st.success("Test notification sent successfully!")
        else:
            st.error("Failed to send notification — check the webhook URL.")

    with st.expander("How to create a Discord webhook"):
        st.markdown("""
1. Open your Discord server and navigate to a channel.
2. Click **Edit Channel** → **Integrations** → **Webhooks** → **New Webhook**.
3. Copy the webhook URL and paste it above.
4. Set `DISCORD_WEBHOOK_URL=<your-url>` in your `.env` file to persist it across sessions.
        """)

    st.markdown("---")
    st.subheader("About")
    st.markdown("""
**KAT Market Screener** — rules-based stock screener.

- Short-term mode: momentum, volume, technicals, catalysts
- Long-term mode: revenue growth, fundamentals, balance sheet, valuation

Run `python main.py --help` for CLI options.
    """)
