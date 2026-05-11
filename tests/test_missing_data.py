"""
Tests for missing data handling. The screener must not crash when data is absent.
Missing fields should degrade gracefully, not raise exceptions.
"""
import pytest
import pandas as pd
from src.scoring import score_short_term, score_long_term
from src.fundamentals import analyze_fundamentals
from src.technicals import calculate_technicals
from src.news import analyze_news, score_earnings_timing
from src.grading import score_to_grade
from src.filters import apply_filters


def _empty_data(**overrides) -> dict:
    """Minimal ticker data with most fields missing (None)."""
    base = {
        "ticker": "MISSING",
        "company_name": "Missing Corp",
        "sector": "Unknown",
        "industry": "Unknown",
        "quote_type": "EQUITY",
        "price": 10.0,
        "market_cap": None,
        "float_shares": None,
        "volume": None,
        "avg_volume": None,
        "rel_volume": None,
        "day_change_pct": None,
        "week52_high": None,
        "week52_low": None,
        "dist_from_52w_high_pct": None,
        "revenue_growth": None,
        "earnings_growth": None,
        "eps": None,
        "pe": None,
        "forward_pe": None,
        "ps_ratio": None,
        "gross_margin": None,
        "operating_margin": None,
        "free_cash_flow": None,
        "total_cash": None,
        "total_debt": None,
        "debt_to_cash": None,
        "short_percent_float": None,
        "earnings_date": None,
        "news_headlines": [],
        "price_history": pd.DataFrame(),
    }
    base.update(overrides)
    return base


class TestMissingDataDoesNotCrash:
    def test_short_term_scoring_all_missing(self):
        data = _empty_data()
        result = score_short_term(data)
        assert isinstance(result["kat_score"], int)
        assert 0 <= result["kat_score"] <= 100

    def test_long_term_scoring_all_missing(self):
        data = _empty_data()
        result = score_long_term(data)
        assert isinstance(result["kat_score"], int)
        assert 0 <= result["kat_score"] <= 100

    def test_analyze_fundamentals_all_missing(self):
        result = analyze_fundamentals(_empty_data())
        assert "fundamental_score" in result
        assert 0 <= result["fundamental_score"] <= 100

    def test_calculate_technicals_empty_history(self):
        result = calculate_technicals(pd.DataFrame(), 10.0)
        assert result["tech_signal"] == "insufficient data"
        assert result["ema9"] is None

    def test_calculate_technicals_none_history(self):
        result = calculate_technicals(None, 10.0)
        assert result["ema9"] is None

    def test_analyze_news_empty_headlines(self):
        result = analyze_news([])
        assert result["catalyst_summary"] == "No recent news found"
        assert isinstance(result["catalyst_score"], int)

    def test_score_earnings_timing_none(self):
        score = score_earnings_timing(None)
        assert isinstance(score, int)
        assert score >= 0

    def test_grade_conversion_zero_score(self):
        grade = score_to_grade(0)
        assert grade == "D"

    def test_filters_with_none_fields(self):
        result = {
            "ticker": "MISSING",
            "price": None,
            "market_cap": None,
            "avg_volume": None,
            "rel_volume": None,
            "revenue_growth": None,
            "pe": None,
            "kat_grade": "D",
            "kat_score": 30,
            "quote_type": "EQUITY",
            "earnings_date": None,
        }
        # Should not crash even with None values and active filters
        filtered = apply_filters([result], {"min_price": 1.0, "min_market_cap": 1_000_000})
        assert isinstance(filtered, list)


class TestMissingDataReducesConfidence:
    def test_all_missing_is_low_confidence(self):
        data = _empty_data()
        result = score_short_term(data)
        assert result["confidence"] == "Low"

    def test_complete_data_is_higher_confidence(self):
        import numpy as np
        prices = [100.0 + i * 0.5 for i in range(60)]
        idx = pd.date_range(end=pd.Timestamp.today(), periods=60, freq="D")
        hist = pd.DataFrame({
            "Close": prices, "Open": prices, "High": prices, "Low": prices,
            "Volume": [2_000_000] * 60,
        }, index=idx)

        data = _empty_data(
            market_cap=5_000_000_000,
            volume=3_000_000,
            avg_volume=1_000_000,
            rel_volume=3.0,
            revenue_growth=25.0,
            pe=25.0,
            gross_margin=60.0,
            operating_margin=15.0,
            free_cash_flow=500_000_000,
            total_cash=2_000_000_000,
            total_debt=300_000_000,
            debt_to_cash=0.15,
            news_headlines=["Company beats expectations", "Revenue grows 30%", "Raises guidance"],
            price_history=hist,
        )
        result = score_short_term(data)
        assert result["confidence"] in ("Medium", "High")


class TestHighGrowthNoPENotHarshlyPenalized:
    def test_high_growth_no_pe_still_reasonable_score(self):
        """High-growth companies with no PE shouldn't be aggressively penalized."""
        data = _empty_data(
            revenue_growth=45.0,
            earnings_growth=None,
            pe=None,  # Unprofitable but high-growth
            forward_pe=None,
            ps_ratio=8.0,
            gross_margin=65.0,
            operating_margin=-5.0,  # Slight operating loss
            total_cash=1_000_000_000,
            total_debt=100_000_000,
            debt_to_cash=0.1,
            free_cash_flow=-50_000_000,  # FCF negative but manageable
            news_headlines=["Revenue beats expectations by 15%"],
        )
        result = score_long_term(data)
        # Should not be in D territory just because PE is missing
        assert result["kat_score"] >= 40


class TestNoCrashOnBadPriceHistory:
    def test_single_row_history(self):
        hist = pd.DataFrame({
            "Close": [100.0], "Open": [99.0], "High": [101.0],
            "Low": [98.0], "Volume": [1_000_000],
        }, index=[pd.Timestamp.today()])
        result = calculate_technicals(hist, 100.0)
        assert isinstance(result, dict)

    def test_history_with_nan_values(self):
        import numpy as np
        prices = [100.0] * 30
        prices[10] = np.nan
        idx = pd.date_range(end=pd.Timestamp.today(), periods=30, freq="D")
        hist = pd.DataFrame({
            "Close": prices, "Open": prices, "High": prices, "Low": prices,
            "Volume": [1_000_000] * 30,
        }, index=idx)
        result = calculate_technicals(hist, 100.0)
        assert isinstance(result, dict)
