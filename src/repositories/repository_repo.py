from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

import asyncpg

from src.domain.models import CrawlCheckpoint, CrawlRun, Repository, StarSnapshot
from src.repositories.base import BaseRepository


class RepositoryRepo(BaseRepository):
    async def bulk_upsert(self, repositories: list[Repository]) -> int:
        if not repositories:
            return 0

        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    """
                    CREATE TEMP TABLE repos_staging (
                        github_id VARCHAR(255),
                        name_with_owner VARCHAR(512),
                        owner VARCHAR(255),
                        name VARCHAR(255),
                        star_count INTEGER,
                        description TEXT,
                        primary_language VARCHAR(100),
                        is_fork BOOLEAN,
                        url TEXT,
                        created_at TIMESTAMPTZ,
                        pushed_at TIMESTAMPTZ
                    ) ON COMMIT DROP
                    """
                )

                records = [
                    (
                        repo.github_id,
                        repo.name_with_owner,
                        repo.owner,
                        repo.name,
                        repo.star_count,
                        repo.description,
                        repo.primary_language,
                        repo.is_fork,
                        repo.url,
                        repo.created_at,
                        repo.pushed_at,
                    )
                    for repo in repositories
                ]

                await conn.copy_records_to_table(
                    "repos_staging",
                    records=records,
                    columns=[
                        "github_id",
                        "name_with_owner",
                        "owner",
                        "name",
                        "star_count",
                        "description",
                        "primary_language",
                        "is_fork",
                        "url",
                        "created_at",
                        "pushed_at",
                    ],
                )

                await conn.execute(
                    """
                    INSERT INTO repositories (
                        github_id, name_with_owner, owner, name, star_count,
                        description, primary_language, is_fork, url,
                        created_at, pushed_at, crawled_at, updated_at
                    )
                    SELECT
                        github_id, name_with_owner, owner, name, star_count,
                        description, primary_language, is_fork, url,
                        created_at, pushed_at, NOW(), NOW()
                    FROM repos_staging
                    ON CONFLICT (github_id) DO UPDATE SET
                        name_with_owner = EXCLUDED.name_with_owner,
                        owner = EXCLUDED.owner,
                        name = EXCLUDED.name,
                        star_count = EXCLUDED.star_count,
                        description = EXCLUDED.description,
                        primary_language = EXCLUDED.primary_language,
                        is_fork = EXCLUDED.is_fork,
                        url = EXCLUDED.url,
                        created_at = EXCLUDED.created_at,
                        pushed_at = EXCLUDED.pushed_at,
                        crawled_at = NOW(),
                        updated_at = NOW()
                    WHERE repositories.star_count IS DISTINCT FROM EXCLUDED.star_count
                       OR repositories.name_with_owner IS DISTINCT FROM EXCLUDED.name_with_owner
                       OR repositories.description IS DISTINCT FROM EXCLUDED.description
                       OR repositories.primary_language IS DISTINCT FROM EXCLUDED.primary_language
                       OR repositories.pushed_at IS DISTINCT FROM EXCLUDED.pushed_at
                    """
                )

                await conn.execute(
                    """
                    INSERT INTO repository_star_snapshots (github_id, star_count, snapshot_date)
                    SELECT github_id, star_count, CURRENT_DATE
                    FROM repos_staging
                    ON CONFLICT (github_id, snapshot_date) DO UPDATE SET
                        star_count = EXCLUDED.star_count
                    WHERE repository_star_snapshots.star_count IS DISTINCT FROM EXCLUDED.star_count
                    """
                )

        return len(repositories)

    async def count(self) -> int:
        async with self._pool.acquire() as conn:
            return await conn.fetchval("SELECT COUNT(*) FROM repositories")

    async def get_by_github_id(self, github_id: str) -> Optional[dict[str, Any]]:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM repositories WHERE github_id = $1",
                github_id,
            )
            return dict(row) if row else None

    async def list_repositories(
        self,
        *,
        page: int = 1,
        size: int = 50,
        language: Optional[str] = None,
        min_stars: Optional[int] = None,
    ) -> tuple[list[dict[str, Any]], int]:
        offset = (page - 1) * size
        conditions: list[str] = []
        params: list[Any] = []

        if language:
            params.append(language)
            conditions.append(f"primary_language = ${len(params)}")

        if min_stars is not None:
            params.append(min_stars)
            conditions.append(f"star_count >= ${len(params)}")

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        count_query = f"SELECT COUNT(*) FROM repositories {where_clause}"
        list_query = f"""
            SELECT *
            FROM repositories
            {where_clause}
            ORDER BY star_count DESC
            LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}
        """

        async with self._pool.acquire() as conn:
            total = await conn.fetchval(count_query, *params)
            rows = await conn.fetch(list_query, *params, size, offset)

        return [dict(row) for row in rows], int(total)

    async def get_star_history(self, github_id: str) -> list[StarSnapshot]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT github_id, star_count, snapshot_date
                FROM repository_star_snapshots
                WHERE github_id = $1
                ORDER BY snapshot_date ASC
                """,
                github_id,
            )

        return [
            StarSnapshot(
                github_id=row["github_id"],
                star_count=row["star_count"],
                snapshot_date=row["snapshot_date"],
            )
            for row in rows
        ]

    async def get_stats(self) -> dict[str, Any]:
        async with self._pool.acquire() as conn:
            total_repos = await conn.fetchval("SELECT COUNT(*) FROM repositories")
            last_crawl = await conn.fetchrow(
                """
                SELECT started_at, completed_at, repos_crawled, status
                FROM crawl_runs
                ORDER BY started_at DESC
                LIMIT 1
                """
            )
            top_languages = await conn.fetch(
                """
                SELECT primary_language, COUNT(*) AS count
                FROM repositories
                WHERE primary_language IS NOT NULL
                GROUP BY primary_language
                ORDER BY count DESC
                LIMIT 10
                """
            )

        return {
            "total_repos": total_repos,
            "last_crawl": dict(last_crawl) if last_crawl else None,
            "top_languages": [dict(row) for row in top_languages],
        }


class CrawlRepo(BaseRepository):
    async def create_run(self, repos_target: int) -> int:
        async with self._pool.acquire() as conn:
            return await conn.fetchval(
                """
                INSERT INTO crawl_runs (repos_target, status)
                VALUES ($1, 'running')
                RETURNING id
                """,
                repos_target,
            )

    async def update_run(
        self,
        run_id: int,
        *,
        repos_crawled: Optional[int] = None,
        status: Optional[str] = None,
        error_message: Optional[str] = None,
        completed: bool = False,
    ) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE crawl_runs
                SET repos_crawled = COALESCE($2, repos_crawled),
                    status = COALESCE($3, status),
                    error_message = COALESCE($4, error_message),
                    completed_at = CASE WHEN $5 THEN NOW() ELSE completed_at END
                WHERE id = $1
                """,
                run_id,
                repos_crawled,
                status,
                error_message,
                completed,
            )

    async def create_checkpoints(self, run_id: int, window_queries: list[str]) -> None:
        async with self._pool.acquire() as conn:
            await conn.executemany(
                """
                INSERT INTO crawl_checkpoints (crawl_run_id, window_query)
                VALUES ($1, $2)
                ON CONFLICT (crawl_run_id, window_query) DO NOTHING
                """,
                [(run_id, query) for query in window_queries],
            )

    async def get_pending_checkpoints(self, run_id: int) -> list[CrawlCheckpoint]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, crawl_run_id, window_query, last_cursor, repos_fetched, completed
                FROM crawl_checkpoints
                WHERE crawl_run_id = $1 AND completed = FALSE
                ORDER BY id ASC
                """,
                run_id,
            )

        return [
            CrawlCheckpoint(
                id=row["id"],
                crawl_run_id=row["crawl_run_id"],
                window_query=row["window_query"],
                last_cursor=row["last_cursor"],
                repos_fetched=row["repos_fetched"],
                completed=row["completed"],
            )
            for row in rows
        ]

    async def update_checkpoint(
        self,
        checkpoint_id: int,
        *,
        last_cursor: Optional[str] = None,
        repos_fetched: Optional[int] = None,
        completed: bool = False,
    ) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE crawl_checkpoints
                SET last_cursor = COALESCE($2, last_cursor),
                    repos_fetched = COALESCE($3, repos_fetched),
                    completed = CASE WHEN $4 THEN TRUE ELSE completed END,
                    updated_at = NOW()
                WHERE id = $1
                """,
                checkpoint_id,
                last_cursor,
                repos_fetched,
                completed,
            )

    async def get_latest_run(self) -> Optional[CrawlRun]:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, started_at, completed_at, repos_crawled, repos_target, status, error_message
                FROM crawl_runs
                ORDER BY started_at DESC
                LIMIT 1
                """
            )

        if not row:
            return None

        return CrawlRun(
            id=row["id"],
            started_at=row["started_at"],
            completed_at=row["completed_at"],
            repos_crawled=row["repos_crawled"],
            repos_target=row["repos_target"],
            status=row["status"],
            error_message=row["error_message"],
        )

    async def ensure_checkpoints(self, run_id: int, window_queries: list[str]) -> None:
        async with self._pool.acquire() as conn:
            existing = await conn.fetchval(
                "SELECT COUNT(*) FROM crawl_checkpoints WHERE crawl_run_id = $1",
                run_id,
            )
            if existing == 0:
                await conn.executemany(
                    """
                    INSERT INTO crawl_checkpoints (crawl_run_id, window_query)
                    VALUES ($1, $2)
                    """,
                    [(run_id, query) for query in window_queries],
                )
