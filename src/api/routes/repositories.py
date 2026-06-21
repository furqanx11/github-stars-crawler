from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from src.config import Settings, get_settings
from src.db.connection import get_pool
from src.repositories.repository_repo import RepositoryRepo
from src.services.repository_service import RepositoryService

router = APIRouter()


def get_repository_service(settings: Settings = Depends(get_settings)) -> RepositoryService:
    pool = get_pool()
    return RepositoryService(RepositoryRepo(pool))


@router.get("/repos")
async def list_repositories(
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    language: Optional[str] = None,
    min_stars: Optional[int] = Query(None, ge=0),
    service: RepositoryService = Depends(get_repository_service),
) -> dict:
    return await service.list_repositories(
        page=page,
        size=size,
        language=language,
        min_stars=min_stars,
    )


@router.get("/repos/{github_id}")
async def get_repository(
    github_id: str,
    service: RepositoryService = Depends(get_repository_service),
) -> dict:
    repo = await service.get_repository(github_id)
    if repo is None:
        raise HTTPException(status_code=404, detail="Repository not found")
    return repo


@router.get("/repos/{github_id}/history")
async def get_repository_history(
    github_id: str,
    service: RepositoryService = Depends(get_repository_service),
) -> dict:
    repo = await service.get_repository(github_id)
    if repo is None:
        raise HTTPException(status_code=404, detail="Repository not found")

    history = await service.get_star_history(github_id)
    return {"github_id": github_id, "history": history}


@router.get("/stats")
async def get_stats(
    service: RepositoryService = Depends(get_repository_service),
) -> dict:
    return await service.get_stats()
