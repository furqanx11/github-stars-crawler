from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from src.infrastructure.rate_limiter import RateLimiter


@pytest.mark.asyncio
async def test_wait_if_needed_does_not_sleep_when_remaining_above_buffer() -> None:
    limiter = RateLimiter(buffer=100)
    reset_at = datetime.now(timezone.utc) + timedelta(hours=1)
    limiter.update_from_response(remaining=5000, reset_at=reset_at)

    start = asyncio.get_event_loop().time()
    await limiter.wait_if_needed()
    elapsed = asyncio.get_event_loop().time() - start

    assert elapsed < 0.1


@pytest.mark.asyncio
async def test_wait_if_needed_sleeps_when_below_buffer(monkeypatch: pytest.MonkeyPatch) -> None:
    limiter = RateLimiter(buffer=100)
    reset_at = datetime.now(timezone.utc) + timedelta(seconds=2)
    limiter.update_from_response(remaining=50, reset_at=reset_at)

    sleep_calls: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    await limiter.wait_if_needed()

    assert len(sleep_calls) == 1
    assert sleep_calls[0] >= 1.0


@pytest.mark.asyncio
async def test_execute_with_retry_succeeds_on_first_attempt() -> None:
    limiter = RateLimiter(buffer=100)
    calls = {"count": 0}

    async def operation() -> str:
        calls["count"] += 1
        return "ok"

    result = await limiter.execute_with_retry(operation)

    assert result == "ok"
    assert calls["count"] == 1
