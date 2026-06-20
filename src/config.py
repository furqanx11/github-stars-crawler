import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


def _env_file() -> str | None:
    """Load .env locally; skip in Docker where compose sets env vars explicitly."""
    if os.getenv("DOCKER") == "1":
        return None
    env_path = Path(".env")
    return str(env_path) if env_path.exists() else None


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_env_file(),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "postgresql://postgres:postgres@localhost:5432/github_stars"
    github_token: str = ""

    crawl_target: int = 100_000
    batch_size: int = 500
    max_concurrency: int = 3
    rate_limit_buffer: int = 100

    api_host: str = "0.0.0.0"
    api_port: int = 8000

    github_graphql_url: str = "https://api.github.com/graphql"
    search_page_size: int = 100


def get_settings() -> Settings:
    return Settings()
