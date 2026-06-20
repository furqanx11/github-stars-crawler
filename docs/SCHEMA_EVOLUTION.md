# Schema Evolution for Extended GitHub Metadata

This document describes how the database schema can evolve to capture issues, pull requests, commits, comments, reviews, and CI checks while keeping updates efficient (minimal rows affected).

## Design Principles

1. **One entity type per table** — avoid wide JSON blobs for queryable metadata.
2. **Natural keys from GitHub** — use GitHub node IDs as stable unique identifiers.
3. **Upsert over delete+insert** — `ON CONFLICT ... DO UPDATE` for idempotent sync.
4. **Append-only for history** — snapshots and events get new rows; mutable state gets upserted.
5. **Minimal row impact** — only changed entities are written.

## Core Entity Model

```text
repositories (existing)
    ├── issues
    ├── pull_requests
    │     ├── pull_request_commits
    │     ├── pull_request_reviews
    │     └── ci_checks
    └── comments (polymorphic)
```

## Proposed Tables

### Issues

```sql
CREATE TABLE issues (
    id              BIGSERIAL PRIMARY KEY,
    github_id       VARCHAR(255) UNIQUE NOT NULL,
    repo_github_id  VARCHAR(255) NOT NULL REFERENCES repositories(github_id),
    number          INTEGER NOT NULL,
    title           TEXT NOT NULL,
    state           VARCHAR(50) NOT NULL,
    comment_count   INTEGER DEFAULT 0,
    created_at      TIMESTAMPTZ,
    updated_at      TIMESTAMPTZ,
    crawled_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(repo_github_id, number)
);
```

### Pull Requests

```sql
CREATE TABLE pull_requests (
    id              BIGSERIAL PRIMARY KEY,
    github_id       VARCHAR(255) UNIQUE NOT NULL,
    repo_github_id  VARCHAR(255) NOT NULL REFERENCES repositories(github_id),
    number          INTEGER NOT NULL,
    title           TEXT NOT NULL,
    state           VARCHAR(50) NOT NULL,
    comment_count   INTEGER DEFAULT 0,
    review_count    INTEGER DEFAULT 0,
    commit_count    INTEGER DEFAULT 0,
    created_at      TIMESTAMPTZ,
    updated_at      TIMESTAMPTZ,
    crawled_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(repo_github_id, number)
);
```

### Commits in Pull Requests

```sql
CREATE TABLE pull_request_commits (
    id              BIGSERIAL PRIMARY KEY,
    pr_github_id    VARCHAR(255) NOT NULL REFERENCES pull_requests(github_id),
    commit_sha      VARCHAR(40) NOT NULL,
    message         TEXT,
    author_login    VARCHAR(255),
    committed_at    TIMESTAMPTZ,
    UNIQUE(pr_github_id, commit_sha)
);
```

### Polymorphic Comments (Issues & PRs)

```sql
CREATE TABLE comments (
    id              BIGSERIAL PRIMARY KEY,
    github_id       VARCHAR(255) UNIQUE NOT NULL,
    parent_type     VARCHAR(20) NOT NULL,  -- 'issue' | 'pull_request'
    parent_github_id VARCHAR(255) NOT NULL,
    author_login    VARCHAR(255),
    body            TEXT,
    created_at      TIMESTAMPTZ,
    updated_at      TIMESTAMPTZ,
    crawled_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_comments_parent ON comments(parent_type, parent_github_id);
```

### PR Reviews

```sql
CREATE TABLE pull_request_reviews (
    id              BIGSERIAL PRIMARY KEY,
    github_id       VARCHAR(255) UNIQUE NOT NULL,
    pr_github_id    VARCHAR(255) NOT NULL REFERENCES pull_requests(github_id),
    author_login    VARCHAR(255),
    state           VARCHAR(50),
    body            TEXT,
    submitted_at    TIMESTAMPTZ,
    crawled_at      TIMESTAMPTZ DEFAULT NOW()
);
```

### CI Checks

```sql
CREATE TABLE ci_checks (
    id              BIGSERIAL PRIMARY KEY,
    pr_github_id    VARCHAR(255) NOT NULL REFERENCES pull_requests(github_id),
    check_name      VARCHAR(255) NOT NULL,
    status          VARCHAR(50) NOT NULL,
    conclusion      VARCHAR(50),
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    crawled_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(pr_github_id, check_name)
);
```

## Efficient Update Patterns

### PR with growing comments (10 today, 20 tomorrow)

On day 1: insert 10 comment rows.
On day 2: fetch comments, compare by `github_id`:

- **10 existing comments**: upsert only if `body` or `updated_at` changed (often 0 rows updated).
- **10 new comments**: 10 INSERTs only.

Existing comment rows are never deleted and re-inserted. Only new/changed rows are touched.

```sql
INSERT INTO comments (github_id, parent_type, parent_github_id, author_login, body, created_at, updated_at)
VALUES ($1, $2, $3, $4, $5, $6, $7)
ON CONFLICT (github_id) DO UPDATE SET
    body = EXCLUDED.body,
    updated_at = EXCLUDED.updated_at,
    crawled_at = NOW()
WHERE comments.body IS DISTINCT FROM EXCLUDED.body
   OR comments.updated_at IS DISTINCT FROM EXCLUDED.updated_at;
```

### Incremental sync cursor

Add a `sync_cursors` table per repo per entity type:

```sql
CREATE TABLE sync_cursors (
    repo_github_id  VARCHAR(255) NOT NULL,
    entity_type     VARCHAR(50) NOT NULL,
    last_synced_at  TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (repo_github_id, entity_type)
);
```

Daily crawl only fetches entities updated since `last_synced_at`.

### Denormalized counters

Update `pull_requests.comment_count` in the same transaction as comment upserts, or via trigger, so list queries avoid JOIN COUNT.

## Migration Strategy

1. Add new tables without altering `repositories`.
2. Backfill metadata per repo in background jobs.
3. Enable incremental sync after backfill completes.
4. Add indexes after bulk load for faster DDL.

## Why This Scales

| Operation | Rows affected |
|-----------|---------------|
| New PR comment | 1 INSERT |
| Updated review | 1 UPDATE (conditional) |
| Unchanged issue | 0 |
| New CI check run | 1 INSERT or 1 upsert on (pr, check_name) |
| Daily star snapshot | 1 upsert per repo per day (existing pattern) |

The schema stays normalized, queryable, and efficient for continuous daily crawls.
