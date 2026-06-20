from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.infrastructure.github_client import GitHubClient, _parse_datetime
from src.infrastructure.rate_limiter import RateLimiter


@pytest.fixture
def rate_limiter() -> RateLimiter:
    return RateLimiter(buffer=100)


@pytest.fixture
def github_client(rate_limiter: RateLimiter) -> GitHubClient:
    return GitHubClient(
        token="test-token",
        graphql_url="https://api.github.com/graphql",
        rate_limiter=rate_limiter,
        page_size=100,
    )


def test_map_search_page_filters_null_nodes(github_client: GitHubClient) -> None:
    payload = {
        "search": {
            "pageInfo": {"hasNextPage": False, "endCursor": "cursor123"},
            "nodes": [
                None,
                {
                    "id": "R_kgDO",
                    "nameWithOwner": "octocat/Hello-World",
                    "owner": {"login": "octocat"},
                    "name": "Hello-World",
                    "stargazerCount": 5000,
                    "description": "My first repo",
                    "url": "https://github.com/octocat/Hello-World",
                    "primaryLanguage": {"name": "JavaScript"},
                    "isFork": False,
                    "createdAt": "2011-01-26T19:01:12Z",
                    "pushedAt": "2011-01-26T19:14:43Z",
                },
                None,
            ],
        },
        "rateLimit": {
            "cost": 1,
            "remaining": 4999,
            "resetAt": "2026-06-20T18:00:00Z",
        },
    }

    page = github_client._map_search_page(payload)

    assert len(page.repositories) == 1
    repo = page.repositories[0]
    assert repo.github_id == "R_kgDO"
    assert repo.name_with_owner == "octocat/Hello-World"
    assert repo.star_count == 5000
    assert repo.primary_language == "JavaScript"
    assert page.has_next_page is False
    assert page.end_cursor == "cursor123"


def test_map_repository_handles_missing_optional_fields(github_client: GitHubClient) -> None:
    node = {
        "id": "R_kgDO2",
        "nameWithOwner": "user/minimal",
        "owner": {"login": "user"},
        "name": "minimal",
        "stargazerCount": 0,
        "description": None,
        "url": None,
        "primaryLanguage": None,
        "isFork": False,
        "createdAt": None,
        "pushedAt": None,
    }

    repo = github_client._map_repository(node)

    assert repo.description is None
    assert repo.primary_language is None
    assert repo.created_at is None


def test_parse_datetime() -> None:
    parsed = _parse_datetime("2026-06-20T18:00:00Z")
    assert parsed == datetime(2026, 6, 20, 18, 0, 0, tzinfo=timezone.utc)
