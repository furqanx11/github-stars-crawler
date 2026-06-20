from __future__ import annotations

import asyncio
from pathlib import Path

import asyncpg

from src.config import get_settings
from src.db.connection import close_pool, create_pool


async def _connect_with_retry(database_url: str, attempts: int = 5) -> asyncpg.Pool:
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            return await create_pool(database_url)
        except (OSError, asyncpg.exceptions.ConnectionDoesNotExistError) as exc:
            last_error = exc
            if attempt < attempts - 1:
                await asyncio.sleep(2**attempt)
    raise last_error or RuntimeError("Failed to connect to database")


async def _run_migrations() -> None:
    settings = get_settings()
    pool = await _connect_with_retry(settings.database_url)

    migration_path = Path(__file__).parent / "migrations" / "001_initial.sql"
    sql = migration_path.read_text(encoding="utf-8")

    async with pool.acquire() as conn:
        await conn.execute(sql)

    await close_pool()
    print("Database schema applied successfully.")


def main() -> None:
    asyncio.run(_run_migrations())


if __name__ == "__main__":
    main()
