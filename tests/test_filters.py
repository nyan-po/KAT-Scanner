"""Tests for filter logic."""
import pytest
from src.filters import apply_filters, sort_results, limit_results, _passes_all


def _make_result(**overrides) -> dict:
    base = {
        "ticker": "TEST",
        "price": 50.0,
        "market_cap": 1_000_000_000,
        "avg_volume": 1_000_000,
        "rel_volume": 2.0,
        "revenue_growth": 20.0,
        "pe": 25.0,
        "kat_grade": "B+",
        "kat_score": 76,
        "quote_type": "EQUITY",
        "earnings_date": None,
    }
    base.update(overrides)
    return base


class TestMinPriceFilter:
    def test_passes_above_min(self):
        r = _make_result(price=10.0)
        assert _passes_all(r, {"min_price": 5.0}) is True

    def test_fails_below_min(self):
        r = _make_result(price=3.0)
        assert _passes_all(r, {"min_price": 5.0}) is False

    def test_passes_when_no_filter(self):
        r = _make_result(price=1.0)
        assert _passes_all(r, {}) is True


class TestMaxPriceFilter:
    def test_passes_below_max(self):
        r = _make_result(price=50.0)
        assert _passes_all(r, {"max_price": 100.0}) is True

    def test_fails_above_max(self):
        r = _make_result(price=150.0)
        assert _passes_all(r, {"max_price": 100.0}) is False


class TestMarketCapFilter:
    def test_passes_above_min(self):
        r = _make_result(market_cap=500_000_000)
        assert _passes_all(r, {"min_market_cap": 100_000_000}) is True

    def test_fails_below_min(self):
        r = _make_result(market_cap=30_000_000)
        assert _passes_all(r, {"min_market_cap": 100_000_000}) is False


class TestRelVolumeFilter:
    def test_passes_above_min(self):
        r = _make_result(rel_volume=2.5)
        assert _passes_all(r, {"min_relative_volume": 2.0}) is True

    def test_fails_below_min(self):
        r = _make_result(rel_volume=1.0)
        assert _passes_all(r, {"min_relative_volume": 1.5}) is False

    def test_passes_when_none_and_no_filter(self):
        r = _make_result(rel_volume=None)
        assert _passes_all(r, {}) is True


class TestGradeFilter:
    def test_b_plus_passes_b_minimum(self):
        r = _make_result(kat_grade="B+")
        assert _passes_all(r, {"min_grade": "B"}) is True

    def test_b_minus_fails_b_plus_minimum(self):
        r = _make_result(kat_grade="B-")
        assert _passes_all(r, {"min_grade": "B+"}) is False

    def test_a_plus_passes_d_minimum(self):
        r = _make_result(kat_grade="A+")
        assert _passes_all(r, {"min_grade": "D"}) is True

    def test_d_fails_c_minimum(self):
        r = _make_result(kat_grade="D")
        assert _passes_all(r, {"min_grade": "C"}) is False


class TestETFFilter:
    def test_etf_excluded_when_flag_set(self):
        r = _make_result(quote_type="ETF")
        assert _passes_all(r, {"exclude_etfs": True}) is False

    def test_etf_passes_when_flag_not_set(self):
        r = _make_result(quote_type="ETF")
        assert _passes_all(r, {"exclude_etfs": False}) is True

    def test_equity_always_passes_etf_filter(self):
        r = _make_result(quote_type="EQUITY")
        assert _passes_all(r, {"exclude_etfs": True}) is True


class TestLowPricedFilter:
    def test_low_priced_excluded_when_flag_set(self):
        r = _make_result(price=3.0)
        assert _passes_all(r, {"exclude_low_priced": True}) is False

    def test_high_priced_always_passes(self):
        r = _make_result(price=20.0)
        assert _passes_all(r, {"exclude_low_priced": True}) is True


class TestApplyFilters:
    def test_returns_passing_subset(self):
        results = [
            _make_result(ticker="A", price=50.0),
            _make_result(ticker="B", price=0.5),  # will fail min_price
        ]
        filtered = apply_filters(results, {"min_price": 1.0})
        tickers = [r["ticker"] for r in filtered]
        assert "A" in tickers
        assert "B" not in tickers

    def test_empty_results(self):
        assert apply_filters([], {"min_price": 1.0}) == []

    def test_all_pass_empty_filters(self):
        results = [_make_result(ticker="A"), _make_result(ticker="B")]
        assert len(apply_filters(results, {})) == 2


class TestSortResults:
    def test_sorts_descending_by_score(self):
        results = [
            _make_result(ticker="A", kat_score=70),
            _make_result(ticker="B", kat_score=90),
            _make_result(ticker="C", kat_score=55),
        ]
        sorted_r = sort_results(results, key="kat_score")
        assert sorted_r[0]["ticker"] == "B"
        assert sorted_r[-1]["ticker"] == "C"


class TestLimitResults:
    def test_limits_to_max(self):
        results = [_make_result(ticker=str(i)) for i in range(20)]
        assert len(limit_results(results, 10)) == 10

    def test_no_limit_when_none(self):
        results = [_make_result(ticker=str(i)) for i in range(20)]
        assert len(limit_results(results, None)) == 20

    def test_no_truncation_when_under_limit(self):
        results = [_make_result(ticker=str(i)) for i in range(5)]
        assert len(limit_results(results, 10)) == 5
