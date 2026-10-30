# TradePilot backend foundation

This directory contains the Phase 5 Node.js/Express API foundation. It exposes
health checks only. It does not connect to PostgreSQL, invoke Python, expose
research artifacts, authenticate users, or produce live trading data.

## Requirements

- Node.js 22 or newer
- npm

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
- `GET /health/ready`: readiness of implemented dependencies. At this step the
  only readiness check is validated configuration.

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
|-- logging/             # structured JSON logger
|-- app.ts               # dependency-injected Express composition
`-- server.ts            # process lifecycle and graceful shutdown
tests/                   # unit and HTTP integration tests
```

## PostgreSQL preparation

`createApp` receives validated dependencies rather than constructing them
inside route modules. A future PostgreSQL connection and readiness probe can be
added through this composition boundary. No database package, configuration,
table, migration, or placeholder repository is included until an approved step
uses it.

Do not implement research formulas in this server. Future research execution
must use the approved versioned Python boundary and preserve Python-generated
dataset and report identities.
