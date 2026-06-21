from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI

from src.api.routes.repositories import router as repositories_router
from src.config import get_settings
from src.db.connection import close_pool, create_pool


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    await create_pool(settings.database_url)
    yield
    await close_pool()


def create_app() -> FastAPI:
    app = FastAPI(
        title="GitHub Stars Crawler API",
        description="Read API for crawled GitHub repository star counts",
        version="1.0.0",
        lifespan=lifespan,
    )
    app.include_router(repositories_router)
    return app
