from __future__ import annotations

import asyncio
import calendar
from datetime import date, timedelta
from typing import Optional

from src.domain.models import CrawlCheckpoint, Repository
from src.infrastructure.github_client import GitHubClient
from src.repositories.repository_repo import CrawlRepo, RepositoryRepo


def _log(message: str) -> None:
    print(message, flush=True)


class CrawlerService:
    GITHUB_LAUNCH = date(2008, 4, 1)

    def __init__(
        self,
        github_client: GitHubClient,
        repository_repo: RepositoryRepo,
        crawl_repo: CrawlRepo,
        *,
        crawl_target: int,
        batch_size: int,
        max_concurrency: int,
    ) -> None:
        self._github_client = github_client
        self._repository_repo = repository_repo
        self._crawl_repo = crawl_repo
        self._crawl_target = crawl_target
        self._batch_size = batch_size
        self._max_concurrency = max_concurrency
        self._repos_crawled = 0
        self._lock = asyncio.Lock()
        self._stop_event = asyncio.Event()

    async def run(self, resume_run_id: Optional[int] = None) -> int:
        if resume_run_id:
            run_id = resume_run_id
            latest = await self._crawl_repo.get_latest_run()
            if latest and latest.id == run_id:
                self._repos_crawled = latest.repos_crawled
        else:
            run_id = await self._crawl_repo.create_run(self._crawl_target)
            windows = generate_search_windows(self.GITHUB_LAUNCH, date.today())
            await self._crawl_repo.ensure_checkpoints(run_id, windows)

        checkpoints = await self._crawl_repo.get_pending_checkpoints(run_id)
        if not checkpoints:
            await self._crawl_repo.update_run(
                run_id,
                repos_crawled=self._repos_crawled,
                status="completed",
                completed=True,
            )
            return self._repos_crawled

        _log(
            f"Starting crawl run {run_id}: target={self._crawl_target:,} repos, "
            f"pending_windows={len(checkpoints)}, concurrency={self._max_concurrency}"
        )

        queue: asyncio.Queue[CrawlCheckpoint] = asyncio.Queue()
        for checkpoint in checkpoints:
            queue.put_nowait(checkpoint)

        async def worker() -> None:
            while not self._stop_event.is_set():
                try:
                    checkpoint = queue.get_nowait()
                except asyncio.QueueEmpty:
                    return
                await self._process_checkpoint(checkpoint, run_id)

        try:
            workers = [
                asyncio.create_task(worker())
                for _ in range(self._max_concurrency)
            ]
            await asyncio.gather(*workers)

            await self._crawl_repo.update_run(
                run_id,
                repos_crawled=self._repos_crawled,
                status="completed",
                completed=True,
            )
        except Exception as exc:
            await self._crawl_repo.update_run(
                run_id,
                repos_crawled=self._repos_crawled,
                status="failed",
                error_message=str(exc),
            )
            raise

        return self._repos_crawled

    async def _process_checkpoint(
        self,
        checkpoint: CrawlCheckpoint,
        run_id: int,
    ) -> None:
        if self._stop_event.is_set():
            return

        cursor = checkpoint.last_cursor
        fetched_in_window = checkpoint.repos_fetched
        pending_batch: list[Repository] = []

        while not self._stop_event.is_set():
            page = await self._github_client.search_repositories(
                checkpoint.window_query,
                after=cursor,
            )

            if not page.repositories:
                break

            for repo in page.repositories:
                if self._stop_event.is_set():
                    break

                pending_batch.append(repo)
                fetched_in_window += 1

                if len(pending_batch) >= self._batch_size:
                    await self._flush_batch(pending_batch, run_id)
                    pending_batch = []

                if await self._should_stop():
                    break

            if pending_batch:
                await self._flush_batch(pending_batch, run_id)
                pending_batch = []

            cursor = page.end_cursor
            await self._crawl_repo.update_checkpoint(
                checkpoint.id,
                last_cursor=cursor,
                repos_fetched=fetched_in_window,
            )

            if not page.has_next_page or await self._should_stop():
                break

        await self._crawl_repo.update_checkpoint(
            checkpoint.id,
            last_cursor=cursor,
            repos_fetched=fetched_in_window,
            completed=True,
        )

    async def _flush_batch(self, batch: list[Repository], run_id: int) -> None:
        if not batch:
            return

        await self._repository_repo.bulk_upsert(batch)
        async with self._lock:
            self._repos_crawled += len(batch)
            await self._crawl_repo.update_run(run_id, repos_crawled=self._repos_crawled)
            if (
                self._repos_crawled % 5000 < len(batch)
                or self._repos_crawled >= self._crawl_target
            ):
                pct = min(100.0, 100.0 * self._repos_crawled / self._crawl_target)
                remaining = self._github_client.rate_limit_remaining
                rate_info = f", rate_limit_remaining={remaining}" if remaining is not None else ""
                _log(
                    f"Progress: {self._repos_crawled:,}/{self._crawl_target:,} repos "
                    f"({pct:.1f}%){rate_info}"
                )

    async def _should_stop(self) -> bool:
        async with self._lock:
            if self._repos_crawled >= self._crawl_target:
                self._stop_event.set()
                return True
        return False


def generate_search_windows(start: date, end: date) -> list[str]:
    """Generate monthly search windows, bisecting dense months into weeks."""
    windows: list[str] = []
    current = date(start.year, start.month, 1)

    while current <= end:
        last_day = calendar.monthrange(current.year, current.month)[1]
        month_end = date(current.year, current.month, last_day)
        if month_end > end:
            month_end = end

        windows.extend(
            _split_window_if_needed(current, month_end)
        )

        if current.month == 12:
            current = date(current.year + 1, 1, 1)
        else:
            current = date(current.year, current.month + 1, 1)

    return windows


def _split_window_if_needed(start: date, end: date) -> list[str]:
    """Return weekly sub-windows for long ranges to stay under the 1,000-result cap."""
    days = (end - start).days + 1
    if days <= 7:
        return [_build_query(start, end)]

    windows: list[str] = []
    current = start
    while current <= end:
        week_end = min(current + timedelta(days=6), end)
        windows.append(_build_query(current, week_end))
        current = week_end + timedelta(days=1)

    return windows


def _build_query(start: date, end: date) -> str:
    return f"is:public created:{start.isoformat()}..{end.isoformat()} sort:stars-desc"
