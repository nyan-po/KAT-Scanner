# KAT Market Screener

A rules-based, market-wide stock screener that discovers stocks across the market and ranks them using the **KAT grading model** (A+ through D).

> **Disclaimer:** This tool is for educational and research purposes only. It is not financial advice. All investment decisions carry risk. Past performance of any grading system does not guarantee future results. Always do your own due diligence.

---

## Overview

KAT Market Screener is a **market-scan-first** tool. Its primary goal is not just to analyze tickers you already know — it's to search the entire market, discover potential movers, grade them, and surface the best short-term and long-term opportunities.

### What it does

- Fetches a broad universe of tickers (S&P 500, Nasdaq 100, small caps) from free public sources
- Downloads price, fundamental, and news data via `yfinance`
- Calculates technical indicators (9 EMA, 20 EMA, 50 SMA, 200 SMA, relative volume, momentum)
- Scores each ticker using a weighted KAT model (0-100) for two modes:
  - **short_term**: Catalyst, volume, technicals, earnings timing, sector momentum
  - **long_term**: Revenue growth, balance sheet, FCF, valuation, sector tailwind
- Converts scores to letter grades (A+ through D)
- Applies configurable filters
- Outputs a ranked terminal table and saves CSV/JSON results

---

## Project Structure

```
KAT-Scanner/
├── main.py                  # CLI entry point
├── config.yaml              # All settings (universe, filters, scoring weights, watchlist)
├── requirements.txt
├── .env.example
├── README.md
├── src/
│   ├── config.py            # Config loader
│   ├── universe.py          # Market universe builder (ticker discovery)
│   ├── data.py              # yfinance data fetching layer
│   ├── technicals.py        # Technical indicator calculations
│   ├── fundamentals.py      # Fundamental analysis signals
│   ├── news.py              # News/catalyst analysis
│   ├── scoring.py           # KAT scoring engine (short_term + long_term)
│   ├── grading.py           # Grade conversion and comparison
│   ├── filters.py           # Filter logic
│   └── output.py            # Terminal table, CSV, JSON output
└── tests/
    ├── test_universe.py
    ├── test_scoring.py
    ├── test_grading.py
    ├── test_filters.py
    └── test_missing_data.py
```

---

## Setup

### Requirements

- Python 3.11+
- Internet connection (for yfinance and Wikipedia ticker lists)

### Install

```bash
# Clone or download the project
cd KAT-Scanner

# Create a virtual environment (recommended)
python -m venv venv
source venv/bin/activate    # macOS/Linux
venv\Scripts\activate       # Windows

# Install dependencies
pip install -r requirements.txt
```

### Environment variables (optional)

```bash
cp .env.example .env
# Edit .env if needed (no paid API keys required for MVP)
```

---

## How to Run

### Default market scan (short-term)

```bash
python main.py
```

This is equivalent to:

```bash
python main.py --scan market --mode short_term
```

### Market scan, long-term mode

```bash
python main.py --scan market --mode long_term
```

### Watchlist scan

```bash
python main.py --scan watchlist --mode short_term
python main.py --scan watchlist --mode long_term
```

### Analyze one or more specific tickers

```bash
python main.py --ticker NVDA --mode long_term
python main.py --ticker APLD SOUN MU --mode short_term
```

### Scan from a CSV file

Your CSV should have ticker symbols in the first column (no header required, or with a header):

```bash
python main.py --csv tickers.csv --mode short_term
```

Example `tickers.csv`:
```
NVDA
AMD
TSLA
AAPL
```

---

## Filtering Examples

### Filter by minimum KAT grade

```bash
python main.py --scan market --mode short_term --min-grade A-
python main.py --scan market --mode long_term --min-grade B+
```

### Filter by minimum market cap

```bash
python main.py --scan market --mode long_term --min-market-cap 500000000
```

### Filter by relative volume (unusual activity)

```bash
python main.py --scan market --mode short_term --min-rel-volume 2.0
```

### Limit results

```bash
python main.py --scan market --mode short_term --max-results 20
```

### Combine multiple filters

```bash
python main.py --scan market --mode short_term \
  --min-grade B \
  --min-rel-volume 1.5 \
  --min-market-cap 100000000 \
  --max-results 30
```

### Exclude ETFs and low-priced stocks

```bash
python main.py --scan market --mode short_term --exclude-etfs --exclude-low-priced
```

---

## How to Adjust Scoring Weights

Edit `config.yaml` under the `scoring` section:

```yaml
scoring:
  short_term:
    catalyst_news: 20        # News/catalyst quality
    relative_volume: 20      # Volume surge signal
    technical_setup: 20      # Technical indicator alignment
    earnings_timing: 15      # Proximity to earnings
    sector_strength: 10      # Sector tailwind
    short_interest: 5        # Short squeeze potential
    options_liquidity: 5     # Placeholder
    risk_penalty: 5          # Risk reduction
  long_term:
    revenue_growth: 20
    earnings_trend: 15
    balance_sheet: 15
    fcf_trend: 15
    valuation: 10
    sector_tailwind: 10
    execution_proxy: 10
    dilution_risk: 5
```

*Note: The weights in config.yaml are for documentation/reference. Actual scoring logic is in `src/scoring.py`. To customize scoring behavior, edit the weight values in `scoring.py`.*

---

## How to Adjust Filters

Edit `config.yaml` under the `filters` section:

```yaml
filters:
  min_price: 1               # Minimum stock price
  max_price: null            # Maximum stock price (null = no limit)
  min_market_cap: 50000000   # Minimum market cap ($50M)
  min_avg_volume: 500000     # Minimum average daily volume
  min_relative_volume: 1.2   # Minimum relative volume vs average
  min_revenue_growth: null   # Minimum revenue growth % (null = no filter)
  max_pe: null               # Maximum PE ratio (null = no filter)
  earnings_within_days: null # Only show stocks with earnings in X days
  min_grade: B               # Minimum KAT grade
  exclude_etfs: false
  exclude_low_priced: false
  max_results: 50
```

All filters can also be overridden via CLI flags (see examples above).

---

## KAT Grades

| Grade | Score Range | Meaning |
|-------|-------------|---------|
| A+    | 90-100      | Exceptional setup — highest conviction |
| A     | 85-89       | Strong setup — high conviction |
| A-    | 80-84       | Good setup — strong but verify entry |
| B+    | 75-79       | Tradable — needs some confirmation |
| B     | 70-74       | Watchlist — wait for trigger |
| B-    | 65-69       | Speculative — small size only |
| C     | 55-64       | Weak setup — mostly avoid |
| D     | 0-54        | Avoid |

### Suggested Action Rules

- **A+ or A** with strong technical: `buy zone`
- **A-**: `wait for entry` (don't chase if extended)
- **B+**: `watchlist` (needs confirmation)
- **B**: `watchlist only`
- **B-**: `speculative` (small size, chart must confirm)
- **C or D**: `avoid`

---

## Limitations of yfinance / Free Data

- **Delay**: yfinance data may be 15 minutes delayed for price and volume.
- **Missing fields**: Many fundamental fields (FCF, debt, short interest) are not available for all tickers. The screener handles this gracefully but confidence scores will be lower.
- **News quality**: Only basic news headlines are available. Catalyst scoring is conservative by default.
- **Earnings dates**: May be missing or approximate.
- **Small caps**: Data quality for small/micro-cap stocks is lower and more fields will be missing.
- **Rate limiting**: Scanning 500 tickers takes several minutes. The screener adds small delays to avoid hitting yfinance rate limits.
- **Real-time data**: This is not a real-time trading tool. Treat results as starting points for your own research.
- **No options data**: Options liquidity is a placeholder score (not calculated from real options data).
- **Wikipedia scraping**: The S&P 500 and Nasdaq-100 ticker lists are scraped from Wikipedia. If Wikipedia changes its page format, parsing may break. The screener will fall back to the watchlist in that case.

---

## Running Tests

```bash
pytest tests/ -v
```

All tests are designed to run without internet access (they mock external data sources).

---

## Output Files

After each scan, the screener saves:

- `screener_results.csv` — Full results with all available fields
- `screener_results.json` — Full results with scan metadata

Both files are saved in the project root by default. You can change the paths in `config.yaml` under `output`.

---

## Watchlist

Edit the `watchlist` section of `config.yaml` to customize your personal watchlist:

```yaml
watchlist:
  - NVDA
  - AMD
  - TSLA
  # Add your own tickers...
```

---

## Sector Mappings

The screener has KAT-defined sector labels that can override yfinance sector labels for more precise tailwind scoring. Edit `sector_mappings` in `config.yaml`:

```yaml
sector_mappings:
  AI Infrastructure:
    - NVDA
    - AMD
    - APLD
  Cybersecurity:
    - CRWD
    - PANW
```

---

*KAT Market Screener is open for personal and educational use. Not for commercial redistribution. This is not financial advice.*
