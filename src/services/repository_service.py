from __future__ import annotations

import asyncio
import calendar
from datetime import date, datetime
from typing import Optional

from src.domain.models import CrawlCheckpoint, Repository
from src.infrastructure.github_client import GitHubClient
from src.repositories.repository_repo import CrawlRepo, RepositoryRepo


class RepositoryService:
    def __init__(self, repository_repo: RepositoryRepo) -> None:
        self._repository_repo = repository_repo

    async def list_repositories(
        self,
        *,
        page: int = 1,
        size: int = 50,
        language: Optional[str] = None,
        min_stars: Optional[int] = None,
    ) -> dict:
        items, total = await self._repository_repo.list_repositories(
            page=page,
            size=size,
            language=language,
            min_stars=min_stars,
        )
        return {
            "items": items,
            "page": page,
            "size": size,
            "total": total,
            "pages": (total + size - 1) // size if size else 0,
        }

    async def get_repository(self, github_id: str) -> Optional[dict]:
        return await self._repository_repo.get_by_github_id(github_id)

    async def get_star_history(self, github_id: str) -> list[dict]:
        snapshots = await self._repository_repo.get_star_history(github_id)
        return [
            {
                "github_id": snapshot.github_id,
                "star_count": snapshot.star_count,
                "snapshot_date": snapshot.snapshot_date.isoformat(),
            }
            for snapshot in snapshots
        ]

    async def get_stats(self) -> dict:
        return await self._repository_repo.get_stats()
