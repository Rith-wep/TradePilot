# TradePilot backend foundation

This directory contains the Phase 5 Node.js/Express API and PostgreSQL catalog
foundation. It exposes health checks and authenticated, read-only historical
research catalog/evidence APIs. Its internal artifact verifier can
invoke the trusted Python verification contract, but it is not exposed through
HTTP. The server does not manage users, run research, or produce live trading
data.

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
- `GET /api/v1/instruments/:symbol`: one verified instrument.
- `GET /api/v1/datasets/:datasetId`: one immutable historical dataset.
- `GET /api/v1/candidate-reports/:reportId`: one candidate-report record.
- `GET /api/v1/candidate-reports/:reportId/candidates`: verified candidate evidence.
- `GET /api/v1/evidence/:candidateEvidenceId`: one verified evidence projection.
- `POST /api/v1/research-jobs`: enqueue an allowlisted request (`researcher` or `admin`; HTTP 202).
- `GET /api/v1/research-jobs/`: list caller-owned jobs; administrators may inspect all jobs.
- `GET /api/v1/research-jobs/:jobId`: owner-or-admin job detail.

All endpoints use the `tradepilot-api/v1` response envelope and return an
`x-request-id` header. Requests may provide a safe `x-request-id`; otherwise the
server creates a UUID.

The health endpoints are intentionally unauthenticated. Every `/api/v1` route
requires an OIDC access token in `Authorization: Bearer <token>` and at least
the `viewer` role. `researcher` and `admin` inherit viewer access; no privileged
write operation exists yet. Roles are accepted only from the configured signed
token claim. Client headers, query parameters, and request bodies cannot grant
roles.

The three catalog endpoints are read-only and support optional `limit` and
`cursor` parameters. Page sizes default to 25 and are capped at 100. Trailing
slash variants are equivalent. Decimal values and PostgreSQL `bigint` values
remain strings; timestamps are UTC ISO 8601 values. See
`docs/contracts/research-catalog-api-v1.md` for response fields.

`HOST` remains restricted to `127.0.0.1`, `::1`, or `localhost` in the current
deployment model. Production catalog access is no longer blanket-disabled: the
process starts only with valid OIDC/JWKS security configuration, and every API
request must authenticate and authorize successfully. Routes expose no storage keys, filesystem paths, raw Parquet, Python
diagnostics, or verification internals. Candidate reports are explicitly
historical research evidence and never live trading signals.

## Authentication and HTTP security

Configure an HTTPS OIDC issuer, the API audience, and the issuer's HTTPS JWKS
URL. Tokens must have a trusted asymmetric algorithm (`RS256`, `PS256`, or
`ES256`), matching issuer/audience, `sub`, `iat`, and unexpired `exp`. Signature
keys are resolved only from the configured JWKS. A missing, malformed, expired,
wrong-issuer, wrong-audience, or invalid-signature token fails closed.

Helmet security headers are enabled, request bodies are bounded, and `/api/v1`
requests have an in-memory bounded rate limit. CORS is deny-by-default for
browser origins: list exact HTTPS origins (or HTTP loopback origins for local
development) in `CORS_ALLOWED_ORIGINS`; wildcards are rejected. The current
rate limiter is per process and is not a distributed abuse-control system.

The server validates bearer tokens only. It has no login flow, refresh-token
handling, user directory, revocation feed, or audit-log sink. TLS termination,
OIDC tenant policy, network controls, distributed rate limiting, key-rotation
monitoring, and authorization administration remain deployment responsibilities.

Candidate evidence is never read directly by Node. The bounded Python evidence
contract verifies the immutable report first, then projects supported fields.
Evidence responses include `classification: "HISTORICAL_RESEARCH"` and
`liveSignal: false`, and omit canonical report JSON and local paths. See
`docs/contracts/candidate-evidence-api-v1.md`.

## Structure

```text
src/
|-- auth/                # OIDC/JWKS verification and role authorization
|-- config/              # validated process configuration
|-- http/contracts/      # versioned response envelopes
|-- http/errors/         # transport-safe errors
|-- http/middleware/     # request IDs, logs, 404 and error handling
|-- http/routes/         # Express routers
|-- database/            # pg pool, migration runner and catalog access
|-- verification/        # internal, schema-checked Python contract adapter
|-- catalog/             # verified, transactional artifact registration
|-- research-jobs/       # durable queue repository and worker lifecycle
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

The production API database role needs `SELECT` and the narrowly required
`INSERT` access on catalog and queue tables. The worker additionally requires
`UPDATE` on `research_jobs` and `INSERT` on `research_job_events`. Neither role
needs `DELETE`, schema ownership, or artifact-root credentials; migration
permissions should belong to a separate operator role. Filesystem permissions
should make artifact roots read-only to Node and Python after publication.

## Durable research-job queue

Migration `002_research_jobs` adds `research_jobs` and append-only lifecycle
records in `research_job_events`. Requests accept only contract version
`tradepilot-research-job-request/v1`, a verified catalog dataset ID, EURUSD or
GBPUSD, H1, and an existing v1 breakout or pullback identifier. No command,
path, executable, arbitrary parameter, or result field is accepted.

Submission is transactional. A per-owner idempotency key is bound to the
request fingerprint. Identical reuse returns the existing job; conflicting
reuse fails. Queue depth and per-owner active counts are checked under a
PostgreSQL advisory transaction lock.

Workers claim rows with `FOR UPDATE SKIP LOCKED`. Claims have random lease
tokens, expirations, bounded attempts, and token-guarded completion. Another
worker may recover an expired lease; stale workers cannot finalize that job.
Only sanitized error codes are persisted.

```powershell
cd server
npm run db:migrate
npm run build
npm run worker
```

The worker invokes only the fixed `tradepilot.execution` Python module with
operator-approved roots. Python verifies the dataset, runs the existing shared
workflow with the approved default v1 configuration, atomically publishes and
verifies the immutable report, and returns its ID. Node independently verifies
and registers that report before completing the job. No user path, command, or
strategy parameter reaches the subprocess.

Workers renew leases during execution. Every renewal, retry, and completion is
fenced by the current lease token. `SUCCEEDED` requires a registered report ID
through a database foreign key. If a worker crashes after publication, the next
attempt deterministically reuses and verifies the same report before completing.
Lease loss is handled as a normal abandoned attempt, so fencing rejection does
not crash the worker loop.

Research jobs pin `TRADEPILOT_IMPLEMENTATION_REVISION` when submitted. Workers
fail closed if that revision differs from their trusted runtime revision. Set it
to the lowercase 40-character build Git SHA in production; when unset and Git
metadata cannot be read, the explicit fallback is `unknown`.
