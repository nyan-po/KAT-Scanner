"""Tests for universe builder."""
import pytest
from unittest.mock import patch, MagicMock
import pandas as pd

from src.universe import (
    _clean_ticker,
    _is_valid_ticker,
    build_universe,
    build_watchlist_universe,
    build_manual_universe,
    build_csv_universe,
    FALLBACK_SMALL_CAPS,
)


class TestCleanTicker:
    def test_strips_whitespace(self):
        assert _clean_ticker("  NVDA  ") == "NVDA"

    def test_uppercases(self):
        assert _clean_ticker("nvda") == "NVDA"

    def test_removes_invalid_chars(self):
        assert _clean_ticker("NV!DA") == "NVDA"

    def test_preserves_dot(self):
        assert _clean_ticker("BRK.B") == "BRK.B"

    def test_empty_string(self):
        assert _clean_ticker("") == ""


class TestIsValidTicker:
    def test_valid_simple(self):
        assert _is_valid_ticker("AAPL") is True

    def test_valid_with_dot(self):
        assert _is_valid_ticker("BRK.B") is True

    def test_too_long(self):
        assert _is_valid_ticker("TOOLONGTICKER") is False

    def test_empty(self):
        assert _is_valid_ticker("") is False

    def test_numbers_only(self):
        assert _is_valid_ticker("1234") is False

    def test_single_letter(self):
        assert _is_valid_ticker("A") is True

    def test_5_letters(self):
        assert _is_valid_ticker("GOOGL") is True


class TestBuildWatchlistUniverse:
    def test_returns_valid_tickers(self):
        wl = ["NVDA", "AMD", "TSLA"]
        result = build_watchlist_universe(wl)
        assert result == ["NVDA", "AMD", "TSLA"]

    def test_cleans_and_filters(self):
        wl = ["nvda", " AMD ", "TOOLONGTICKER123"]
        result = build_watchlist_universe(wl)
        assert "NVDA" in result
        assert "AMD" in result
        assert "TOOLONGTICKER123" not in result

    def test_empty_list(self):
        assert build_watchlist_universe([]) == []


class TestBuildManualUniverse:
    def test_basic(self):
        result = build_manual_universe(["AAPL", "MSFT"])
        assert result == ["AAPL", "MSFT"]

    def test_deduplication_not_done_here(self):
        result = build_manual_universe(["AAPL", "aapl"])
        assert result == ["AAPL", "AAPL"]


class TestBuildUniverse:
    def test_falls_back_to_watchlist_when_all_sources_fail(self):
        universe_cfg = {
            "include_sp500": True,
            "include_nasdaq100": True,
            "include_small_caps": False,
            "include_watchlist": True,
            "max_tickers_per_scan": 500,
        }
        watchlist = ["NVDA", "AMD", "TSLA"]

        with patch("src.universe.fetch_sp500_tickers", return_value=[]):
            with patch("src.universe.fetch_nasdaq100_tickers", return_value=[]):
                result = build_universe(universe_cfg, watchlist)

        assert "NVDA" in result
        assert "AMD" in result
        assert "TSLA" in result

    def test_deduplicates(self):
        universe_cfg = {
            "include_sp500": True,
            "include_nasdaq100": True,
            "include_small_caps": False,
            "include_watchlist": True,
            "max_tickers_per_scan": 500,
        }
        watchlist = ["NVDA"]

        with patch("src.universe.fetch_sp500_tickers", return_value=["NVDA", "AAPL"]):
            with patch("src.universe.fetch_nasdaq100_tickers", return_value=["NVDA", "MSFT"]):
                result = build_universe(universe_cfg, watchlist)

        assert result.count("NVDA") == 1

    def test_respects_max_tickers(self):
        universe_cfg = {
            "include_sp500": True,
            "include_nasdaq100": False,
            "include_small_caps": False,
            "include_watchlist": False,
            "max_tickers_per_scan": 10,
        }
        big_list = [f"T{i:04d}" for i in range(1, 100) if _is_valid_ticker(f"T{i:04d}")]

        with patch("src.universe.fetch_sp500_tickers", return_value=big_list[:50]):
            result = build_universe(universe_cfg, [])

        assert len(result) <= 10

    def test_returns_empty_when_no_sources_and_no_watchlist(self):
        universe_cfg = {
            "include_sp500": True,
            "include_nasdaq100": False,
            "include_small_caps": False,
            "include_watchlist": True,
            "max_tickers_per_scan": 500,
        }
        with patch("src.universe.fetch_sp500_tickers", return_value=[]):
            result = build_universe(universe_cfg, [])

        assert result == []
