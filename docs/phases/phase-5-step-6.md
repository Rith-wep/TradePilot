# Phase 5, Step 6: Trusted Artifact Catalog Registration

Status: implemented, pending review and commit.

## Scope

This step adds a bounded verifier waiting queue and an internal service that
registers verified immutable datasets and candidate reports in PostgreSQL. It
does not add HTTP write routes, workers, authentication, research execution, or
frontend behavior.

## Registration flow

1. Accept an immutable artifact ID and only the locator fields required by the
   existing verification contract.
2. Run a fresh, bounded Python verification.
3. Validate the verified identity, integrity metadata, schema fields, timestamp
   range, Decimal strings, and provenance.
4. Derive the storage key from fixed internal prefixes and verified metadata.
5. Open a PostgreSQL transaction and insert with parameterized SQL.
6. Reuse an identical row or reject conflicting immutable metadata.

Candidate reports require their dataset to be registered first. The report's
dataset ID, checksum, instrument, and timeframe must match that catalog row.

## Capacity control

`TRADEPILOT_VERIFIER_MAX_CONCURRENCY` bounds running Python processes and
`TRADEPILOT_VERIFIER_MAX_PENDING_REQUESTS` bounds queued requests. Excess work
fails with the typed, retryable `VERIFIER_OVERLOADED` error. The default limits
are two running and sixteen waiting requests.

## Freshness and reconciliation

Every registration attempt is freshly verified. The first successful insert's
verification time is retained for idempotency; it is not a perpetual assertion
about mutable filesystem state. A future reconciliation job must reverify
catalog entries, compare all immutable fields, report missing or corrupted
artifacts, and require operator action. It must never rewrite IDs or silently
accept drift.

## Permissions

- Artifact roots should be read-only after immutable publication.
- Python and Node receive only approved artifact roots.
- The runtime database role should use least-privilege `SELECT` and `INSERT`.
- Registration errors do not expose paths, credentials, stderr, or stack traces.

## Tests

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

Coverage includes valid and duplicate registration, unregistered report
datasets, missing and corrupted artifacts, identity mismatch, immutable
metadata conflicts, concurrent registration, and verifier overload.

## Limitations

- Registration remains an internal method with no HTTP or worker integration.
- Reconciliation is documented but not implemented.
- Verification starts a Python process for each attempt.
- PostgreSQL and filesystem publication cannot share one atomic transaction;
  reconciliation is required to detect later external filesystem damage.
