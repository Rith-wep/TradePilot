# Phase 5, Step 2: Backend Foundation

**Status:** Complete  
**Scope:** Node.js, Express, and strict TypeScript foundation only. No database,
authentication, Python worker, research APIs, frontend, or live trading data.

## Goal

Create a small production-minded HTTP foundation that future backend steps can
extend without duplicating Python research formulas or weakening immutable
dataset and report identities.

## Architecture

```text
HTTP request
    |
    v
request ID -> structured request log -> JSON body limit
    |
    v
Express route
    |
    +-- GET /health/live
    `-- GET /health/ready
    |
    v
tradepilot-api/v1 success or error envelope
    |
    v
centralized 404/error handling
```

Application composition is separated from process startup. `createApp`
receives validated configuration and a logger, which provides a clean boundary
for future PostgreSQL and service dependencies without creating unused database
objects now.

## Implemented behavior

- Strict TypeScript configuration with additional index, optional-property,
  fallthrough, casing, and unknown-error checks.
- Environment validation for `NODE_ENV`, `PORT`, and `LOG_LEVEL`.
- Native optional `.env` loading for local startup; container/process
  environment variables remain the production boundary.
- Safe caller-provided request IDs or generated UUIDs.
- Structured JSON request, lifecycle, and error logging.
- Versioned `tradepilot-api/v1` success and error envelopes.
- Centralized not-found, malformed-JSON, and unexpected-error handling.
- Disabled Express technology disclosure header.
- Graceful `SIGINT` and `SIGTERM` server shutdown.

Readiness reports only dependencies that actually exist. In this step that is
validated configuration; it does not claim PostgreSQL or Python readiness.

## Endpoints

```text
GET /health/live
GET /health/ready
```

Example success shape:

```json
{
  "apiVersion": "tradepilot-api/v1",
  "requestId": "generated-or-supplied-id",
  "data": {
    "status": "UP",
    "service": "tradepilot-server"
  },
  "meta": {
    "generatedAt": "UTC timestamp"
  }
}
```

No endpoint returns prices, candidates, evidence, simulated signals, or live
market information.

## Main files

```text
server/package.json
server/package-lock.json
server/tsconfig.json
server/.env.example
server/README.md
server/src/app.ts
server/src/server.ts
server/src/config/env.ts
server/src/logging/logger.ts
server/src/http/contracts/envelope.ts
server/src/http/errors/api-error.ts
server/src/http/middleware/
server/src/http/routes/health.ts
server/tests/config.test.ts
server/tests/health.test.ts
```

The repository `.gitignore` excludes backend dependencies, compiled output,
and local `.env` secrets.

## Setup and commands

```powershell
cd server
Copy-Item .env.example .env
npm install
npm run typecheck
npm test
npm run build
npm start
```

PowerShell environments that block the `npm.ps1` wrapper can use `npm.cmd` for
the same commands.

## Verification results

- `npm.cmd run typecheck`: passed.
- `npm.cmd test`: 7 tests passed.
- `npm.cmd run build`: passed.
- Python full suite: 234 tests passed, 2 credential-gated OANDA tests skipped.
- `git diff --check`: passed.

The HTTP tests cover liveness, readiness, success envelopes, safe and unsafe
request IDs, not-found errors, malformed JSON errors, and removal of the
`x-powered-by` header. Configuration tests cover defaults and invalid values.

## Technical decisions

- Express is the only runtime package.
- Environment validation and structured logging use project code rather than
  extra libraries at this small scale.
- Tests use Node's built-in test runner and Supertest.
- The lockfile is committed for reproducible dependency installation.
- PostgreSQL remains an approved future dependency, but no client, connection,
  migration, repository, or table is added before it is used.
- Python research remains the only future source of research calculations and
  content identities.

## Limitations

- There is no PostgreSQL connectivity or readiness probe.
- There is no authentication, authorization, rate limiting, CORS policy, or
  reverse-proxy configuration.
- There are no artifact, instrument, dataset, candidate, or evidence APIs.
- There is no Python contract runner or background worker.
- There is no Docker or CI configuration yet.
- The standalone registry audit could not be repeated through the restricted
  environment, although dependency installation reported zero vulnerabilities.

## Next step

Stop here and request approval before adding PostgreSQL integration, artifact
catalogs, research contracts, authentication, or worker execution.

