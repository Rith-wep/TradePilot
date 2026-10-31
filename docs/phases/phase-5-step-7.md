# Phase 5, Step 7: Read-only Research Catalog APIs

Status: implemented, pending review and commit.

## Scope

This step exposes versioned, read-only Express collections for instruments,
immutable historical datasets, and historical candidate reports. Data comes
only from the trusted PostgreSQL catalog. No public write, verification,
research-execution, authentication, or frontend functionality was added.

## Endpoints

- `GET /api/v1/instruments`
- `GET /api/v1/datasets`
- `GET /api/v1/candidate-reports`

Each endpoint also accepts a trailing slash. Responses use the existing API v1
envelope, request IDs, structured request logging, and centralized typed errors.

## Pagination and validation

Collections use deterministic keyset pagination ordered by symbol or immutable
ID. `limit` defaults to 25 and cannot exceed 100. Cursors are versioned,
endpoint-specific opaque values. Unknown query parameters, repeated values,
invalid limits, malformed cursors, and cross-endpoint cursors fail with HTTP
400.

## Data safety

- Decimal pip sizes and `bigint` row counts remain strings.
- Timestamps are serialized as UTC ISO 8601 values.
- Dataset and report schema versions and verification timestamps are included.
- Historical and synthetic classifications are explicit.
- Candidate reports include `liveSignal: false`.
- Storage keys, paths, Parquet, and verifier internals are omitted.
- Database errors map to a generic retryable `CATALOG_UNAVAILABLE` response.

## Local-only security

The server validates `HOST` as loopback-only and defaults to `127.0.0.1`.
Catalog routes are disabled when `NODE_ENV=production` until authorization is
implemented. PostgreSQL's development port is also published on loopback only.
Operators must not expose these endpoints through a reverse proxy or tunnel.

## Verification commands

```powershell
cd server
docker compose up -d postgres
$env:TEST_DATABASE_URL = "postgresql://tradepilot:tradepilot@localhost:54329/tradepilot"
npm test
npm run typecheck
npm run build

cd ..\research
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## Limitations

- Authentication and authorization are not implemented.
- There are no item-detail endpoints or filtering beyond pagination.
- Catalog reconciliation remains a future internal operation.
- Catalog verification timestamps do not guarantee continuing filesystem
  integrity after registration.
