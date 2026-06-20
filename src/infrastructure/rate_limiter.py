from __future__ import annotations

import asyncio
import random
from datetime import datetime, timezone
from typing import Any, Callable, TypeVar

T = TypeVar("T")


class RateLimiter:
    """Tracks GitHub GraphQL rate limit budget and applies backoff when needed."""

    def __init__(self, buffer: int = 100) -> None:
        self._buffer = buffer
        self._remaining: int | None = None
        self._reset_at: datetime | None = None
        self._lock = asyncio.Lock()

    @property
    def remaining(self) -> int | None:
        return self._remaining

    def update_from_response(self, remaining: int, reset_at: datetime) -> None:
        self._remaining = remaining
        self._reset_at = reset_at

    async def wait_if_needed(self) -> None:
        async with self._lock:
            if self._remaining is None or self._remaining > 0:
                return

            if self._reset_at is None:
                await asyncio.sleep(1.0)
                return

            now = datetime.now(timezone.utc)
            reset_at = self._reset_at
            if reset_at.tzinfo is None:
                reset_at = reset_at.replace(tzinfo=timezone.utc)

            sleep_seconds = max((reset_at - now).total_seconds(), 1.0)
            await asyncio.sleep(sleep_seconds)

    async def execute_with_retry(
        self,
        operation: Callable[[], Any],
        *,
        max_retries: int = 5,
        base_delay: float = 2.0,
        max_delay: float = 32.0,
    ) -> T:
        last_error: Exception | None = None

        for attempt in range(max_retries + 1):
            await self.wait_if_needed()
            try:
                result = operation()
                if asyncio.iscoroutine(result):
                    return await result
                return result
            except RateLimitExceeded as exc:
                last_error = exc
                delay = min(base_delay * (2**attempt), max_delay)
                await asyncio.sleep(delay + random.uniform(0, 0.5))
            except TransientGitHubError as exc:
                last_error = exc
                delay = min(base_delay * (2**attempt), max_delay)
                await asyncio.sleep(delay + random.uniform(0, 0.5))

        raise last_error or RuntimeError("Operation failed after retries")


class RateLimitExceeded(Exception):
    """Raised when GitHub returns a rate limit response."""


class TransientGitHubError(Exception):
    """Raised for retryable server/network failures."""
