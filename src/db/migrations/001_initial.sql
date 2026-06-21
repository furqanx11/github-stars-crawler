CREATE TABLE IF NOT EXISTS repositories (
    id              BIGSERIAL PRIMARY KEY,
    github_id       VARCHAR(255) UNIQUE NOT NULL,
    name_with_owner VARCHAR(512)        NOT NULL,
    owner           VARCHAR(255)        NOT NULL,
    name            VARCHAR(255)        NOT NULL,
    star_count      INTEGER             NOT NULL DEFAULT 0,
    description     TEXT,
    primary_language VARCHAR(100),
    is_fork         BOOLEAN             DEFAULT FALSE,
    url             TEXT,
    created_at      TIMESTAMPTZ,
    pushed_at       TIMESTAMPTZ,
    crawled_at      TIMESTAMPTZ         NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ         NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_repos_stars ON repositories(star_count DESC);
CREATE INDEX IF NOT EXISTS idx_repos_owner ON repositories(owner);
CREATE INDEX IF NOT EXISTS idx_repos_language ON repositories(primary_language);
CREATE INDEX IF NOT EXISTS idx_repos_crawled_at ON repositories(crawled_at DESC);

CREATE TABLE IF NOT EXISTS repository_star_snapshots (
    id              BIGSERIAL PRIMARY KEY,
    github_id       VARCHAR(255) NOT NULL REFERENCES repositories(github_id),
    star_count      INTEGER      NOT NULL,
    snapshot_date   DATE         NOT NULL DEFAULT CURRENT_DATE,
    UNIQUE(github_id, snapshot_date)
);

CREATE TABLE IF NOT EXISTS crawl_runs (
    id              BIGSERIAL PRIMARY KEY,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at    TIMESTAMPTZ,
    repos_crawled   INTEGER     DEFAULT 0,
    repos_target    INTEGER     DEFAULT 100000,
    status          VARCHAR(50) DEFAULT 'running',
    error_message   TEXT
);

CREATE TABLE IF NOT EXISTS crawl_checkpoints (
    id              BIGSERIAL PRIMARY KEY,
    crawl_run_id    BIGINT      NOT NULL REFERENCES crawl_runs(id),
    window_query    TEXT        NOT NULL,
    last_cursor     TEXT,
    repos_fetched   INTEGER     DEFAULT 0,
    completed       BOOLEAN     DEFAULT FALSE,
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(crawl_run_id, window_query)
);

CREATE INDEX IF NOT EXISTS idx_checkpoints_run ON crawl_checkpoints(crawl_run_id, completed);
