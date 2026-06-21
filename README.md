# GitHub Stars Crawler

A production-grade Python service that crawls GitHub repository star counts via the GraphQL API, stores them in PostgreSQL, and exposes a FastAPI read API.

## Features

- **GraphQL crawler** with adaptive date-range windowing (100K repos target)
- **Rate limit handling** with token bucket, exponential backoff, and retry
- **Checkpoint resume** — failed crawls resume from last cursor, not from zero
- **High-throughput upserts** via PostgreSQL COPY + temp table merge
- **Daily snapshots** for star count trend analysis
- **FastAPI read API** for querying crawled data
- **GitHub Actions CI/CD** with Postgres service container
- **Docker Compose** for local development

## Architecture

Clean Architecture with separation of concerns:

```
src/
├── domain/          # Immutable domain models
├── infrastructure/  # ACL: GitHub API client, rate limiter
├── repositories/    # Data access layer (COPY upserts, queries)
├── services/        # Business logic (crawler orchestration, read service)
├── api/             # FastAPI routes
└── db/              # Migrations, setup, dump utilities
```

## Quick Start

### Prerequisites

- Python 3.11+
- Docker & Docker Compose (optional)
- GitHub token (or use `GITHUB_TOKEN` in Actions)

### Local Setup

```bash
cp .env.example .env
# Edit .env and set GITHUB_TOKEN

pip install -r requirements.txt
python -m src.main setup
python -m src.main crawl
python -m src.main serve
```

API available at `http://localhost:8000/docs`

### Docker Compose

```bash
export GITHUB_TOKEN=your_token_here
docker compose up --build
```

Services:
- `db` — PostgreSQL 15
- `setup` — applies migrations
- `crawler` — runs crawl job
- `api` — FastAPI on port 8000

## CLI Commands

| Command | Description |
|---------|-------------|
| `python -m src.main setup` | Apply database migrations |
| `python -m src.main crawl` | Crawl repositories |
| `python -m src.main crawl --resume` | Resume incomplete crawl |
| `python -m src.main serve` | Start FastAPI server |
| `python -m src.db.dump --output repos_dump.csv` | Export data to CSV |

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/repos` | Paginated repo list (`?language=Python&min_stars=1000`) |
| GET | `/repos/{github_id}` | Single repository |
| GET | `/repos/{github_id}/history` | Star count snapshots |
| GET | `/stats` | Crawl statistics |

## Configuration

See [`.env.example`](.env.example):

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql://...` | Postgres connection string |
| `GITHUB_TOKEN` | — | GitHub API token |
| `CRAWL_TARGET` | `100000` | Target repo count |
| `BATCH_SIZE` | `500` | Rows per COPY batch |
| `MAX_CONCURRENCY` | `3` | Parallel search windows |
| `RATE_LIMIT_BUFFER` | `100` | Pause when remaining points below this |

## Database Schema

- `repositories` — current repo metadata and star counts
- `repository_star_snapshots` — daily star count history
- `crawl_runs` — crawl job tracking with progress
- `crawl_checkpoints` — per-window cursor for resume

## GitHub Actions

Workflow [`.github/workflows/crawl.yml`](.github/workflows/crawl.yml):

1. Postgres service container
2. Dependency install
3. `setup-postgres` — create schema
4. `crawl-stars` — fetch 100K repos via GraphQL
5. Dump DB to CSV and upload artifact
6. Run unit tests

Uses default `GITHUB_TOKEN` — no elevated permissions or secrets required.

## Tests

```bash
pytest tests/unit -v

# Integration tests (requires running Postgres)
RUN_INTEGRATION_TESTS=1 pytest tests/integration -v
```

## Documentation

- [docs/SCALABILITY.md](docs/SCALABILITY.md) — scaling to 500M repositories
- [docs/SCHEMA_EVOLUTION.md](docs/SCHEMA_EVOLUTION.md) — future metadata schema design

## Performance

With 5,000 GraphQL points/hour (authenticated):

- ~1,000 API calls for 100K repos (100 repos/page)
- Expected crawl duration: **~20 minutes** including DB writes

## License

MIT
