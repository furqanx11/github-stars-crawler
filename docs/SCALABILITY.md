# Scaling GitHub Stars Crawler to 500 Million Repositories

This document describes what would change if the crawler were scaled from 100,000 to 500 million repositories.

## 1. Distributed Crawling Architecture

At 500M repos, a single process and token cannot finish in reasonable time.

- **Worker fleet**: Deploy many crawler workers (Kubernetes jobs, ECS tasks, or bare-metal workers).
- **Work queue**: Use Redis/RabbitMQ/SQS to distribute search windows or repo IDs to workers.
- **Token pool**: Rotate across many GitHub Apps or PATs to increase aggregate rate limits.
- **Idempotent workers**: Each worker claims a checkpoint/window, processes it, and marks completion.

## 2. Data Partitioning

PostgreSQL single-table writes become a bottleneck at this scale.

- **Partition `repositories` by hash(github_id) or star-range** for faster upserts and vacuum.
- **Separate hot vs cold storage**: recent star changes in OLTP Postgres; historical snapshots in columnar storage (BigQuery, ClickHouse, Parquet on S3).
- **Sharding**: multiple Postgres clusters keyed by repo ID prefix.

## 3. Ingestion Pipeline

COPY + upsert remains valid but must be batched at scale.

- **Stream ingestion**: Kafka/Kinesis between crawler and DB writers.
- **Dedicated writer service**: decouple API fetch from DB commit for backpressure control.
- **Bulk load windows**: periodic COPY into staging tables, merge during low-traffic periods.

## 4. Crawl Strategy Changes

Search API windowing alone is insufficient at 500M scale.

- **GitHub Archive / GH Archive + BigQuery** for bulk historical discovery.
- **Event-driven updates**: webhooks for high-churn repos instead of full rescans.
- **Incremental refresh**: only re-fetch repos where `pushed_at` or `updated_at` changed since last crawl.
- **Priority tiers**: star-count tiers (top 1M daily, long tail weekly/monthly).

## 5. Rate Limit & Reliability

- **Central rate-limit coordinator** shared across workers (Redis token bucket).
- **Dead-letter queue** for failed windows with automatic retry scheduling.
- **Checkpoint store** in durable KV (Postgres/DynamoDB) with lease-based claiming.

## 6. API & Query Layer

- **Read replicas** for FastAPI queries.
- **Search index** (Elasticsearch/Meilisearch) for text and faceted filters.
- **Materialized views** for stats dashboards (top languages, star distribution).

## 7. Observability & Operations

- Metrics: crawl throughput, API points consumed, upsert latency, queue depth.
- Alerting on stalled checkpoints and rate-limit saturation.
- Cost controls: autoscale workers down when queue is empty.

## 8. Estimated Timeline Difference

| Scale | Approx. API calls | Single token (5k pts/hr) | 50 tokens + 100 workers |
|-------|-------------------|--------------------------|-------------------------|
| 100K  | ~1,000            | ~20 minutes              | minutes                 |
| 500M  | ~5,000,000        | ~42 days                 | hours to days           |

At 500M repos, the system becomes a **distributed data platform**, not a single-script crawler.
