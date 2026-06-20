from __future__ import annotations

from datetime import date

from src.services.crawler_service import _build_query, generate_search_windows


def test_build_query_format() -> None:
    query = _build_query(date(2024, 1, 1), date(2024, 1, 7))
    assert query == "is:public created:2024-01-01..2024-01-07 sort:stars-desc"


def test_generate_search_windows_produces_non_empty_list() -> None:
    windows = generate_search_windows(date(2024, 1, 1), date(2024, 1, 31))
    assert len(windows) > 0
    assert all("is:public" in window for window in windows)
    assert all("created:" in window for window in windows)


def test_generate_search_windows_splits_month_into_weeks() -> None:
    windows = generate_search_windows(date(2024, 1, 1), date(2024, 1, 31))
    # January has 31 days -> split into weekly windows
    assert len(windows) >= 4


def test_windows_have_no_duplicate_queries() -> None:
    windows = generate_search_windows(date(2024, 6, 1), date(2024, 6, 30))
    assert len(windows) == len(set(windows))
