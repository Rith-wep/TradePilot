# TradePilot backend foundation

This directory contains the Phase 5 Node.js/Express API and PostgreSQL catalog
foundation. It exposes health checks only. Its internal artifact verifier can
invoke the trusted Python verification contract, but it is not exposed through
HTTP. The server does not run research, authenticate users, or produce live
trading data.

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
- `GET /api/v1/instruments`: verified instrument metadata.
- `GET /api/v1/datasets`: immutable historical dataset metadata.
- `GET /api/v1/candidate-reports`: historical research-candidate metadata.

All endpoints use the `tradepilot-api/v1` response envelope and return an
`x-request-id` header. Requests may provide a safe `x-request-id`; otherwise the
server creates a UUID.

The three catalog endpoints are read-only and support optional `limit` and
`cursor` parameters. Page sizes default to 25 and are capped at 100. Trailing
slash variants are equivalent. Decimal values and PostgreSQL `bigint` values
remain strings; timestamps are UTC ISO 8601 values. See
`docs/contracts/research-catalog-api-v1.md` for response fields.

Until authentication is implemented, `HOST` must be `127.0.0.1`, `::1`, or
`localhost`. Catalog routes return `CATALOG_API_DISABLED` in production even on
loopback. They expose no storage keys, filesystem paths, raw Parquet, Python
diagnostics, or verification internals. Candidate reports are explicitly
historical research evidence and never live trading signals.

## Structure

```text
src/
|-- config/              # validated process configuration
|-- http/contracts/      # versioned response envelopes
|-- http/errors/         # transport-safe errors
|-- http/middleware/     # request IDs, logs, 404 and error handling
|-- http/routes/         # Express routers
|-- database/            # pg pool, migration runner and catalog access
|-- verification/        # internal, schema-checked Python contract adapter
|-- catalog/             # verified, transactional artifact registration
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

## Internal artifact verification

`ArtifactVerifierService` sends one `tradepilot-artifact-verification/v1`
request to the fixed Python module `tradepilot.contracts`. The child process is
launched with an argument array and `shell: false`; clients cannot supply an
executable, module, path, or argument. Configure the trusted executable,
working directory, schema directory, and artifact roots with the
`TRADEPILOT_*` values shown in `.env.example`.

Both messages are validated against the schemas in `research/contracts`.
Input, stdout, stderr, execution time, and concurrent children are bounded.
Timeouts and limit violations terminate the process tree. Contract errors are
mapped to internal typed errors whose messages contain no filesystem paths,
credentials, Python diagnostics, or stack traces. Exact Decimal values remain
JSON strings. The child receives a small operating-system environment allowlist
rather than database credentials or the server's complete environment.

This service is deliberately not wired into Express or PostgreSQL. Verified
metadata is consumed only by the internal catalog-registration service; neither
service is wired into Express.

## Trusted catalog registration

`CatalogRegistrationService` accepts only an immutable ID plus the dataset
locator fields required by the v1 verifier. It performs fresh Python integrity
verification for every registration attempt, derives every database field from
the verified response, and builds storage keys from fixed internal prefixes.
Caller paths and caller-supplied catalog metadata are not accepted.

Dataset and candidate-report writes use one PostgreSQL transaction and
parameterized queries. Re-registering identical content returns `EXISTING`;
different metadata for the same immutable ID fails closed. A candidate report
can be registered only after its referenced dataset exists in the verified
catalog and its checksum, instrument, and timeframe provenance agree.

`integrity_verified_at` records the registration attempt that first published
the immutable row. It is evidence of that verification, not a guarantee that a
filesystem remains unchanged forever. Reconciliation should periodically run
the Python verifier against catalog entries, compare immutable metadata, and
raise an operator-visible discrepancy without updating identities or silently
deleting history.

The production database role should have only `SELECT` and `INSERT` on catalog
tables plus sequence/migration permissions where operationally required. It
does not need `UPDATE`, `DELETE`, schema ownership, or access to artifact-root
credentials. Filesystem permissions should make artifact roots read-only to the
Node service and Python verifier after immutable publication.
