from __future__ import annotations

import argparse
import asyncio
import csv
from pathlib import Path

from src.config import get_settings
from src.db.connection import close_pool, create_pool


async def _dump(output_path: Path) -> None:
    settings = get_settings()
    pool = await create_pool(settings.database_url)

    query = """
        SELECT
            github_id,
            name_with_owner,
            owner,
            name,
            star_count,
            description,
            primary_language,
            is_fork,
            url,
            created_at,
            pushed_at,
            crawled_at,
            updated_at
        FROM repositories
        ORDER BY star_count DESC
    """

    async with pool.acquire() as conn:
        rows = await conn.fetch(query)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        if rows:
            writer.writerow(rows[0].keys())
            for row in rows:
                writer.writerow([row[key] for key in row.keys()])

    await close_pool()
    print(f"Exported {len(rows)} repositories to {output_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Dump repositories table to CSV")
    parser.add_argument("--output", default="repos_dump.csv", help="Output CSV path")
    args = parser.parse_args()
    asyncio.run(_dump(Path(args.output)))


if __name__ == "__main__":
    main()
