# Phase 5, Step 3: PostgreSQL Foundation

**Status:** Complete
**Scope:** PostgreSQL connectivity and verified-artifact catalog metadata only.
No artifact APIs, authentication, workers, research jobs, or Python changes.

## Architecture

```text
Express process
  |-- GET /health/live  -----------------> no database access
  `-- GET /health/ready -> bounded SELECT 1 -> 200 UP / 503 DOWN

explicit migration CLI -> transactional versioned SQL

approved future verifier
  -> parameterized catalog repository
  -> instruments / datasets / candidate_reports metadata

Parquet datasets and canonical report JSON remain authoritative
```

The `pg` driver is the only new runtime dependency. Pool creation, health,
migrations, and catalog queries are separated from HTTP routing.

## Schema decisions

### `instruments`

Stores symbol, base/quote currencies, pip-size string, and price precision.
Currency and symbol formats, positive Decimal syntax, distinct currencies, and
precision range are database constraints.

### `datasets`

Stores the immutable dataset ID, canonical checksum, instrument reference,
provider, timeframe, coverage timestamps, row-count string-compatible bigint,
schema version, safe relative artifact key, synthetic label, and integrity
verification time.

It does not store candles, Parquet bytes, source CSV content, or provider
credentials.

### `candidate_reports`

Stores the immutable report ID, dataset reference, strategy/version,
configuration fingerprint, schema version, signal count, safe relative artifact
key, and integrity verification time.

It does not store canonical report JSON, signals, rule evidence, indicators, or
performance content.

Dataset IDs, report IDs, canonical checksums, and configuration fingerprints
are constrained to lowercase 64-character hexadecimal SHA-256 strings. Artifact
keys must be relative POSIX-style keys without traversal segments.

## Migrations

```text
server/migrations/001_catalog.up.sql
server/migrations/001_catalog.down.sql
```

The migration runner uses a PostgreSQL transaction and transaction-scoped
advisory lock. Applied versions are recorded in `schema_migrations`. Applying
an already-applied migration is deterministic and returns no changes. Rollback
reverses the latest applied migration where its explicit down file permits.

## Environment

```text
DATABASE_URL
DATABASE_CONNECT_TIMEOUT_MS=3000
DATABASE_READY_TIMEOUT_MS=1000
```

The database URL is required and must use `postgres:` or `postgresql:`. Connect,
query, and statement timeouts bound readiness work. Liveness remains independent
and does not invoke the database probe.

## Local commands

```powershell
cd server
docker compose up -d postgres
Copy-Item .env.example .env
npm run db:migrate

$env:TEST_DATABASE_URL = "postgresql://tradepilot:tradepilot@localhost:54329/tradepilot"
npm run typecheck
npm test
npm run build

npm run db:rollback
```

## Tests

The Node suite covers:

- required and malformed database configuration;
- bounded connectivity failure;
- database-ready and database-down HTTP readiness;
- database-independent liveness;
- transactional and idempotent migration application;
- explicit rollback;
- exact ID, checksum, Decimal, timestamp, row-count, artifact-key, foreign-key,
  uniqueness, and signal-count constraints;
- parameterized insert and lookup behavior.

The real PostgreSQL integration test runs in a random temporary schema and
removes it afterward. Without `TEST_DATABASE_URL`, only that test is skipped.

## Limitations

- No API currently reads or writes catalog records.
- No process automatically discovers or catalogs artifacts.
- Integrity verification must be connected through the approved future Python
  contract before production catalog insertion.
- Catalog metadata is logically immutable through the repository, but dedicated
  production database roles and update/delete privileges are not configured.
- Docker Compose is for local PostgreSQL only; API/worker containers and CI are
  not included.
- No authentication, authorization, rate limiting, backup policy, or production
  TLS configuration is implemented.

## Next step

Stop for approval before implementing secure artifact discovery, read-only
catalog APIs, Python contracts, workers, authentication, or research jobs.
