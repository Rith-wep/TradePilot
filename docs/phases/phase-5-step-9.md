# Phase 5, Step 9: API Authentication and Production Security Foundation

Status: complete. Committed as `90d4961`.

## Scope

This step protects every research catalog and candidate-evidence API with
standards-based OIDC access-token verification and least-privilege roles. Health
checks remain separate and unauthenticated. No user database, login flow,
research execution, frontend, or trading execution was added.

## Security model

- JWT signatures are verified against the configured issuer's HTTPS JWKS.
- Issuer, audience, expiration, subject, issued-at time, and an explicit
  asymmetric algorithm allowlist are enforced.
- `viewer`, `researcher`, and `admin` form an ordered role hierarchy. Current
  read-only APIs require `viewer`; higher roles add no write capability yet.
- Roles come only from the verified configured token claim.
- Missing, malformed, expired, wrongly scoped, or invalidly signed tokens fail
  closed with safe versioned API errors.
- Helmet headers, strict CORS origins, bounded JSON bodies, and API rate limits
  apply centrally. Request IDs and structured logging remain enabled.
- Valid authentication configuration is required even in development. There is
  no permissive bypass. The process remains loopback-bound in this milestone.

## Configuration

Set `OIDC_ISSUER`, `OIDC_AUDIENCE`, and `OIDC_JWKS_URL`. Optional controls are
`OIDC_ALLOWED_ALGORITHMS`, `OIDC_ROLES_CLAIM`, `OIDC_JWKS_TIMEOUT_MS`,
`CORS_ALLOWED_ORIGINS`, `RATE_LIMIT_WINDOW_MS`, `RATE_LIMIT_MAX`, and
`REQUEST_BODY_MAX_BYTES`. See `server/.env.example` for safe examples.

## Verification commands

```powershell
cd server
npm run typecheck
npm run build
$env:TEST_DATABASE_URL = "postgresql://tradepilot:tradepilot@localhost:54329/tradepilot"
npm test

cd ..\research
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## Threat assumptions and limitations

The configured OIDC provider, its JWKS endpoint, deployment TLS termination,
and operator-controlled environment are trusted. The JWKS client caches keys
and supports normal key rotation, but this milestone has no revocation feed or
rotation alarm. Rate limits are in-memory per process. There is no distributed
edge protection, user lifecycle, refresh-token handling, security-event sink,
or resource-level ownership policy. Historical research evidence remains
explicitly non-live and is not a trading recommendation.
