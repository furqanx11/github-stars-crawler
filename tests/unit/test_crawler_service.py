from __future__ import annotations

from datetime import date

from src.services.crawler_service import (
    _build_query,
    bisect_window_query,
    generate_search_windows,
    parse_window_dates,
    should_bisect_window,
)


def test_build_query_format() -> None:
    query = _build_query(date(2024, 1, 1), date(2024, 1, 7))
    assert query == "is:public created:2024-01-01..2024-01-07 sort:stars-desc"


def test_generate_search_windows_produces_non_empty_list() -> None:
    windows = generate_search_windows(date(2024, 1, 1), date(2024, 1, 31))
    assert len(windows) > 0
    assert all("is:public" in window for window in windows)
    assert all("created:" in window for window in windows)


def test_generate_search_windows_uses_monthly_granularity() -> None:
    windows = generate_search_windows(date(2024, 1, 1), date(2024, 3, 31))
    assert len(windows) == 3


def test_windows_have_no_duplicate_queries() -> None:
    windows = generate_search_windows(date(2024, 6, 1), date(2024, 6, 30))
    assert len(windows) == len(set(windows))


def test_parse_window_dates() -> None:
    query = _build_query(date(2024, 1, 1), date(2024, 1, 31))
    assert parse_window_dates(query) == (date(2024, 1, 1), date(2024, 1, 31))


def test_should_bisect_window() -> None:
    multi_day = _build_query(date(2024, 1, 1), date(2024, 1, 31))
    single_day = _build_query(date(2024, 1, 1), date(2024, 1, 1))
    assert should_bisect_window(multi_day) is True
    assert should_bisect_window(single_day) is False


def test_bisect_window_query_splits_in_half() -> None:
    query = _build_query(date(2024, 1, 1), date(2024, 1, 10))
    parts = bisect_window_query(query)
    assert len(parts) == 2
    assert all("created:" in part for part in parts)
