from __future__ import annotations

import asyncio
import sys

import typer
import uvicorn

from src.api.app import create_app
from src.config import get_settings
from src.db.connection import close_pool, create_pool
from src.infrastructure.github_client import GitHubClient
from src.infrastructure.rate_limiter import RateLimiter
from src.repositories.repository_repo import CrawlRepo, RepositoryRepo
from src.services.crawler_service import CrawlerService

app = typer.Typer(help="GitHub Stars Crawler CLI")


@app.command()
def setup() -> None:
    """Apply database migrations."""
    from src.db.setup import main as setup_main

    setup_main()


@app.command()
def crawl(
    resume: bool = typer.Option(False, help="Resume the latest incomplete crawl run"),
) -> None:
    """Crawl GitHub repositories and store star counts."""
    asyncio.run(_run_crawl(resume=resume))


@app.command()
def serve() -> None:
    """Start the FastAPI read API."""
    settings = get_settings()
    api = create_app()
    uvicorn.run(api, host=settings.api_host, port=settings.api_port)


async def _run_crawl(resume: bool = False) -> None:
    settings = get_settings()

    if not settings.github_token:
        typer.echo("GITHUB_TOKEN is required", err=True)
        raise typer.Exit(code=1)

    pool = await create_pool(settings.database_url)

    rate_limiter = RateLimiter(buffer=settings.rate_limit_buffer)
    github_client = GitHubClient(
        token=settings.github_token,
        graphql_url=settings.github_graphql_url,
        rate_limiter=rate_limiter,
        page_size=settings.search_page_size,
    )

    repository_repo = RepositoryRepo(pool)
    crawl_repo = CrawlRepo(pool)

    resume_run_id = None
    if resume:
        latest = await crawl_repo.get_latest_run()
        if latest and latest.status == "running":
            resume_run_id = latest.id
            typer.echo(f"Resuming crawl run {resume_run_id}")

    crawler = CrawlerService(
        github_client=github_client,
        repository_repo=repository_repo,
        crawl_repo=crawl_repo,
        crawl_target=settings.crawl_target,
        batch_size=settings.batch_size,
        max_concurrency=settings.max_concurrency,
    )

    try:
        total = await crawler.run(resume_run_id=resume_run_id)
        typer.echo(f"Crawl completed: {total} repositories processed")
    finally:
        await close_pool()


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] in {"setup", "crawl", "serve"}:
        app()
    elif len(sys.argv) > 1:
        app()
    else:
        app()


if __name__ == "__main__":
    main()
