from __future__ import annotations

from abc import ABC

import asyncpg


class BaseRepository(ABC):
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool
