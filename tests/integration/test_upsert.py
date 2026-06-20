from __future__ import annotations

import os

import pytest

from src.domain.models import Repository

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_INTEGRATION_TESTS") != "1",
    reason="Set RUN_INTEGRATION_TESTS=1 and DATABASE_URL to run integration tests",
)


@pytest.mark.asyncio
async def test_bulk_upsert_idempotency_stub() -> None:
    """Integration stub: verifies COPY upsert against a real Postgres instance."""
    from src.config import get_settings
    from src.db.connection import close_pool, create_pool
    from src.repositories.repository_repo import RepositoryRepo

    settings = get_settings()
    pool = await create_pool(settings.database_url)
    repo = RepositoryRepo(pool)

    sample = Repository(
        github_id="R_test_integration",
        name_with_owner="test/integration-repo",
        owner="test",
        name="integration-repo",
        star_count=42,
        description="integration test",
        primary_language="Python",
        is_fork=False,
        url="https://github.com/test/integration-repo",
        created_at=None,
        pushed_at=None,
    )

    try:
        count_first = await repo.bulk_upsert([sample])
        count_second = await repo.bulk_upsert([sample])

        assert count_first == 1
        assert count_second == 1

        stored = await repo.get_by_github_id("R_test_integration")
        assert stored is not None
        assert stored["star_count"] == 42
    finally:
        async with pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM repository_star_snapshots WHERE github_id = $1",
                "R_test_integration",
            )
            await conn.execute(
                "DELETE FROM repositories WHERE github_id = $1",
                "R_test_integration",
            )
        await close_pool()
