from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional


@dataclass(frozen=True, slots=True)
class Repository:
    github_id: str
    name_with_owner: str
    owner: str
    name: str
    star_count: int
    description: Optional[str] = None
    primary_language: Optional[str] = None
    is_fork: bool = False
    url: Optional[str] = None
    created_at: Optional[datetime] = None
    pushed_at: Optional[datetime] = None


@dataclass(frozen=True, slots=True)
class StarSnapshot:
    github_id: str
    star_count: int
    snapshot_date: date


@dataclass(frozen=True, slots=True)
class CrawlRun:
    id: Optional[int]
    started_at: datetime
    completed_at: Optional[datetime]
    repos_crawled: int
    repos_target: int
    status: str
    error_message: Optional[str] = None


@dataclass(frozen=True, slots=True)
class CrawlCheckpoint:
    id: Optional[int]
    crawl_run_id: int
    window_query: str
    last_cursor: Optional[str]
    repos_fetched: int
    completed: bool


@dataclass(frozen=True, slots=True)
class RateLimitInfo:
    cost: int
    remaining: int
    reset_at: datetime


@dataclass(frozen=True, slots=True)
class SearchPage:
    repositories: tuple[Repository, ...]
    has_next_page: bool
    end_cursor: Optional[str]
    rate_limit: RateLimitInfo
