from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

import aiohttp

from src.domain.models import RateLimitInfo, Repository, SearchPage
from src.infrastructure.rate_limiter import RateLimitExceeded, RateLimiter, TransientGitHubError

SEARCH_QUERY = """
query SearchRepos($query: String!, $first: Int!, $after: String) {
  search(query: $query, type: REPOSITORY, first: $first, after: $after) {
    pageInfo {
      hasNextPage
      endCursor
    }
    nodes {
      ... on Repository {
        id
        nameWithOwner
        owner { login }
        name
        stargazerCount
        description
        url
        primaryLanguage { name }
        isFork
        createdAt
        pushedAt
      }
    }
  }
  rateLimit {
    cost
    remaining
    resetAt
  }
}
"""


class GitHubClient:
    """Anti-corruption layer for GitHub GraphQL API."""

    def __init__(
        self,
        token: str,
        graphql_url: str,
        rate_limiter: RateLimiter,
        page_size: int = 100,
    ) -> None:
        self._token = token
        self._graphql_url = graphql_url
        self._rate_limiter = rate_limiter
        self._page_size = page_size

    async def search_repositories(
        self,
        query: str,
        after: Optional[str] = None,
    ) -> SearchPage:
        variables = {
            "query": query,
            "first": self._page_size,
            "after": after,
        }

        payload = await self._rate_limiter.execute_with_retry(
            lambda: self._post_graphql(SEARCH_QUERY, variables)
        )
        return self._map_search_page(payload)

    async def _post_graphql(self, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                self._graphql_url,
                json={"query": query, "variables": variables},
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=60),
            ) as response:
                if response.status in {403, 429}:
                    raise RateLimitExceeded(f"Rate limited with status {response.status}")
                if response.status >= 500:
                    raise TransientGitHubError(f"GitHub server error: {response.status}")

                body = await response.json()

        if "errors" in body:
            messages = [error.get("message", "") for error in body["errors"]]
            if any("rate limit" in message.lower() for message in messages):
                raise RateLimitExceeded("; ".join(messages))
            raise TransientGitHubError("; ".join(messages))

        return body["data"]

    def _map_search_page(self, data: dict[str, Any]) -> SearchPage:
        search = data["search"]
        page_info = search["pageInfo"]
        rate_limit = data["rateLimit"]

        reset_at = _parse_datetime(rate_limit["resetAt"])
        rate_limit_info = RateLimitInfo(
            cost=rate_limit["cost"],
            remaining=rate_limit["remaining"],
            reset_at=reset_at,
        )
        self._rate_limiter.update_from_response(rate_limit_info.remaining, reset_at)

        repositories = tuple(
            self._map_repository(node)
            for node in search.get("nodes", [])
            if node is not None
        )

        return SearchPage(
            repositories=repositories,
            has_next_page=page_info["hasNextPage"],
            end_cursor=page_info.get("endCursor"),
            rate_limit=rate_limit_info,
        )

    @staticmethod
    def _map_repository(node: dict[str, Any]) -> Repository:
        primary_language = node.get("primaryLanguage")
        owner = node.get("owner") or {}

        return Repository(
            github_id=node["id"],
            name_with_owner=node["nameWithOwner"],
            owner=owner.get("login", ""),
            name=node["name"],
            star_count=node.get("stargazerCount", 0),
            description=node.get("description"),
            primary_language=primary_language.get("name") if primary_language else None,
            is_fork=bool(node.get("isFork", False)),
            url=node.get("url"),
            created_at=_parse_datetime(node["createdAt"]) if node.get("createdAt") else None,
            pushed_at=_parse_datetime(node["pushedAt"]) if node.get("pushedAt") else None,
        )


def _parse_datetime(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed
