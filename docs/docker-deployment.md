# Docker deployment

## Prerequisites

- Docker Engine or Docker Desktop with Compose v2.
- Approved dataset and candidate-report host directories.
- A trusted OIDC issuer, audience, and HTTPS JWKS URL.
- A clean full lowercase Git commit SHA.
- Four strong, distinct PostgreSQL passwords.

Create the untracked files listed in `server/secrets/README.md`, then export:

```powershell
$env:TRADEPILOT_IMPLEMENTATION_REVISION = (git rev-parse HEAD).Trim()
$env:TRADEPILOT_DATA_HOST_PATH = "D:\tradepilot\data"
$env:TRADEPILOT_REPORT_HOST_PATH = "D:\tradepilot\reports"
$env:OIDC_ISSUER = "https://identity.example.com"
$env:OIDC_AUDIENCE = "tradepilot-api"
$env:OIDC_JWKS_URL = "https://identity.example.com/.well-known/jwks.json"
```

Never build a production image from a dirty tree. CI should inject its trusted
commit SHA rather than discovering it inside an image.

## Build, migrate, and start

From `server/`:

```powershell
docker compose build api worker
docker compose up -d postgres migrations
docker compose up -d api worker
docker compose ps
```

API and worker startup depends on successful migrations. The base file publishes
no host ports. Add `-f compose.dev.yaml` only for loopback local development.

## Stop and remove

```powershell
docker compose stop api worker
docker compose down
```

Do not use `down -v` where the PostgreSQL volume must survive. The integration
script removes volumes only from its isolated temporary run.

## Roles and migrations

`tradepilot_migrator` owns schema changes. `tradepilot_api` reads the catalog
and submits jobs but cannot mutate catalog records or worker lifecycle fields.
`tradepilot_worker` claims jobs and registers verified artifacts but cannot
alter the schema. Rollbacks are explicit and should be rehearsed against a
restored backup.

## Backup considerations

- Back up PostgreSQL using `pg_dump` or managed snapshots.
- Back up immutable dataset and report roots without rewriting content.
- Keep manifests, canonical JSON, Parquet, checksums, and identity directories
  together.
- Restore into isolation and verify every artifact before enabling API/worker
  access.
- A catalog without its referenced artifacts is not a healthy restoration.

## Full-system integration test

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\docker-integration.ps1
```

It uses generated synthetic data and temporary secrets and cleans up afterward.
Use `-Keep` only for diagnosis, then explicitly remove retained resources.

## Troubleshooting

- Migration failure: inspect `docker compose logs migrations postgres` and
  confirm all secret files existed before the database volume was initialized.
- API unhealthy: inspect `/health/live`, `/health/ready`, database grants, and
  OIDC trust configuration.
- Repeated lost leases: compare lease and execution timeouts and inspect CPU or
  event-loop saturation.
- `IMPLEMENTATION_REVISION_MISMATCH`: deploy API and worker from the same SHA;
  never rewrite a queued job's pin.
- Artifact failure: preserve it for audit and restore only verified immutable
  content.
- JWKS TLS failure: install the legitimate CA chain; never disable production
  TLS verification.
