"""Tests for KAT scoring engine."""
import pytest
import pandas as pd
import numpy as np
from unittest.mock import patch

from src.scoring import score_short_term, score_long_term, _volume_score, _short_interest_score


def _make_price_history(n: int = 60, trend: str = "up") -> pd.DataFrame:
    """Create synthetic price history."""
    prices = []
    base = 100.0
    for i in range(n):
        if trend == "up":
            base *= 1.002
        elif trend == "down":
            base *= 0.998
        prices.append(base)

    idx = pd.date_range(end=pd.Timestamp.today(), periods=n, freq="D")
    df = pd.DataFrame({
        "Close": prices,
        "Open": [p * 0.99 for p in prices],
        "High": [p * 1.01 for p in prices],
        "Low": [p * 0.98 for p in prices],
        "Volume": [1_000_000] * n,
    }, index=idx)
    return df


def _make_good_ticker_data(**overrides) -> dict:
    base = {
        "ticker": "TEST",
        "company_name": "Test Corp",
        "sector": "Technology",
        "industry": "Software",
        "quote_type": "EQUITY",
        "price": 50.0,
        "market_cap": 5_000_000_000,
        "float_shares": 100_000_000,
        "volume": 3_000_000,
        "avg_volume": 1_000_000,
        "rel_volume": 3.0,
        "day_change_pct": 5.0,
        "week52_high": 60.0,
        "week52_low": 30.0,
        "dist_from_52w_high_pct": -16.7,
        "revenue_growth": 30.0,
        "earnings_growth": 25.0,
        "eps": 2.0,
        "pe": 25.0,
        "forward_pe": 20.0,
        "ps_ratio": 5.0,
        "gross_margin": 65.0,
        "operating_margin": 20.0,
        "free_cash_flow": 500_000_000,
        "total_cash": 2_000_000_000,
        "total_debt": 500_000_000,
        "debt_to_cash": 0.25,
        "short_percent_float": 5.0,
        "earnings_date": None,
        "news_headlines": ["Company beats Q2 revenue estimates", "Raises guidance"],
        "price_history": _make_price_history(60, "up"),
    }
    base.update(overrides)
    return base


class TestVolumeScore:
    def test_very_high_rel_vol(self):
        assert _volume_score(6.0, 2_000_000) == 20

    def test_moderate_rel_vol(self):
        score = _volume_score(2.0, 1_000_000)
        assert score == 14

    def test_low_rel_vol(self):
        score = _volume_score(0.5, 1_000_000)
        assert score == 2

    def test_none_rel_vol(self):
        score = _volume_score(None, 1_000_000)
        assert score == 5

    def test_thin_market_penalty(self):
        score_thin = _volume_score(3.0, 50_000)
        score_normal = _volume_score(3.0, 1_000_000)
        assert score_thin < score_normal


class TestShortInterestScore:
    def test_high_short_interest(self):
        assert _short_interest_score(30.0) == 5

    def test_moderate_short_interest(self):
        assert _short_interest_score(18.0) == 4

    def test_low_short_interest(self):
        assert _short_interest_score(5.0) == 1

    def test_none(self):
        assert _short_interest_score(None) == 2


class TestShortTermScoring:
    def test_good_data_scores_well(self):
        data = _make_good_ticker_data()
        result = score_short_term(data)
        assert result["kat_score"] >= 50
        assert result["mode"] == "short_term"
        assert "setup_type" in result
        assert "suggested_action" in result
        assert "confidence" in result

    def test_score_is_bounded(self):
        data = _make_good_ticker_data()
        result = score_short_term(data)
        assert 0 <= result["kat_score"] <= 100

    def test_bad_data_scores_lower(self):
        good = _make_good_ticker_data()
        bad = _make_good_ticker_data(
            revenue_growth=-20.0,
            rel_volume=0.3,
            day_change_pct=-10.0,
            news_headlines=[],
            price_history=_make_price_history(60, "down"),
            debt_to_cash=10.0,
        )
        good_score = score_short_term(good)["kat_score"]
        bad_score = score_short_term(bad)["kat_score"]
        assert good_score > bad_score

    def test_earnings_date_boosts_score(self):
        from datetime import date, timedelta
        near_earnings = (date.today() + timedelta(days=3)).isoformat()
        with_earnings = _make_good_ticker_data(earnings_date=near_earnings)
        without_earnings = _make_good_ticker_data(earnings_date=None)
        assert score_short_term(with_earnings)["kat_score"] >= score_short_term(without_earnings)["kat_score"]

    def test_dilution_flag_reduces_score(self):
        clean = _make_good_ticker_data(news_headlines=["Company beats revenue expectations"])
        dilution = _make_good_ticker_data(news_headlines=["Company announces secondary offering"])
        clean_score = score_short_term(clean)["kat_score"]
        dilution_score = score_short_term(dilution)["kat_score"]
        assert clean_score >= dilution_score


class TestLongTermScoring:
    def test_good_fundamentals_score_well(self):
        data = _make_good_ticker_data()
        result = score_long_term(data)
        assert result["kat_score"] >= 50
        assert result["mode"] == "long_term"

    def test_score_is_bounded(self):
        data = _make_good_ticker_data()
        result = score_long_term(data)
        assert 0 <= result["kat_score"] <= 100

    def test_high_revenue_growth_scores_better(self):
        low_growth = _make_good_ticker_data(revenue_growth=5.0)
        high_growth = _make_good_ticker_data(revenue_growth=50.0)
        assert score_long_term(high_growth)["kat_score"] > score_long_term(low_growth)["kat_score"]

    def test_negative_revenue_growth_penalized(self):
        positive = _make_good_ticker_data(revenue_growth=20.0)
        negative = _make_good_ticker_data(revenue_growth=-15.0)
        assert score_long_term(positive)["kat_score"] > score_long_term(negative)["kat_score"]

    def test_strong_balance_sheet_scores_better(self):
        weak_bs = _make_good_ticker_data(debt_to_cash=8.0, total_cash=100_000_000, total_debt=800_000_000)
        strong_bs = _make_good_ticker_data(debt_to_cash=0.2, total_cash=2_000_000_000, total_debt=400_000_000)
        assert score_long_term(strong_bs)["kat_score"] > score_long_term(weak_bs)["kat_score"]


class TestScoringModesDiffer:
    def test_short_and_long_produce_different_modes(self):
        data = _make_good_ticker_data()
        st = score_short_term(data)
        lt = score_long_term(data)
        assert st["mode"] == "short_term"
        assert lt["mode"] == "long_term"

    def test_short_term_has_volume_components(self):
        data = _make_good_ticker_data()
        result = score_short_term(data)
        assert "score_volume" in result
        assert "score_catalyst" in result

    def test_long_term_has_fundamental_components(self):
        data = _make_good_ticker_data()
        result = score_long_term(data)
        assert "score_revenue" in result
        assert "score_balance_sheet" in result
        assert "score_fcf" in result
