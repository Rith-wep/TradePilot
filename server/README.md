# TradePilot backend foundation

This directory contains the Phase 5 Node.js/Express API and PostgreSQL catalog
foundation. It exposes health checks only. It does not invoke Python, expose
research artifacts, authenticate users, or produce live trading data.

## Requirements

- Node.js 22 or newer
- npm
- Docker Desktop or another PostgreSQL 17-compatible server for integration tests

## Setup

```powershell
cd server
Copy-Item .env.example .env
npm install
npm run typecheck
npm test
npm run build
```

`npm start` uses Node's native optional `.env` loading. Values supplied by the
process or container environment remain the production configuration boundary:

```powershell
npm run build
npm start
```

Endpoints:

- `GET /health/live`: process liveness.
- `GET /health/ready`: validated configuration and bounded PostgreSQL
  connectivity. Database failure returns HTTP 503 with `status: DOWN`.

Both endpoints use the `tradepilot-api/v1` response envelope and return an
`x-request-id` header. Requests may provide a safe `x-request-id`; otherwise the
server creates a UUID.

## Structure

```text
src/
|-- config/              # validated process configuration
|-- http/contracts/      # versioned response envelopes
|-- http/errors/         # transport-safe errors
|-- http/middleware/     # request IDs, logs, 404 and error handling
|-- http/routes/         # Express routers
|-- database/            # pg pool, migration runner and catalog access
|-- logging/             # structured JSON logger
|-- app.ts               # dependency-injected Express composition
`-- server.ts            # process lifecycle and graceful shutdown
tests/                   # unit and HTTP integration tests
```

## PostgreSQL

Start the local service and apply migrations:

```powershell
cd server
docker compose up -d postgres
Copy-Item .env.example .env
npm run db:migrate
```

Roll back the latest migration:

```powershell
npm run db:rollback
```

Migration `001_catalog` creates only `instruments`, `datasets`, and
`candidate_reports`, plus the migration ledger. PostgreSQL stores verified
metadata references. Parquet candles and canonical candidate-report JSON remain
authoritative and are not copied into the database.

Immutable IDs and checksums are lowercase 64-character SHA-256 strings. Decimal
instrument metadata such as `pip_size` is stored as validated text so formatting
is never routed through a JavaScript number. `row_count` is returned as a string
because PostgreSQL `bigint` may exceed JavaScript's safe integer range.

The repository has no artifact discovery or automatic cataloging. Callers must
first verify artifacts through the future approved Python boundary and provide
an `integrity_verified_at` timestamp.

Run integration tests against the local container:

```powershell
$env:TEST_DATABASE_URL = "postgresql://tradepilot:tradepilot@localhost:54329/tradepilot"
npm test
```

Without `TEST_DATABASE_URL`, the isolated PostgreSQL integration test is
skipped while unit and HTTP tests continue to run. Integration tests create a
random schema and remove it afterward; they do not modify the normal `public`
schema.

Do not implement research formulas in this server. Future research execution
must use the approved versioned Python boundary and preserve Python-generated
dataset and report identities.
