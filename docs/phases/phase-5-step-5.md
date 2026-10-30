# Phase 5, Step 5: Controlled Node/Python Verification Adapter

Status: implemented, pending review and commit.

## Scope

The Node backend now has an internal TypeScript adapter for the versioned
Python artifact-verification contract. It verifies existing immutable datasets
and candidate reports. It does not expose an HTTP endpoint, execute research,
or insert catalog rows.

## Trust boundary

- The operator supplies the Python executable, research working directory,
  contract schema directory, dataset root, and report root through trusted
  environment configuration.
- A caller supplies only the versioned request containing an immutable artifact
  ID and the dataset locator fields allowed by the Python v1 contract.
- The Python module is fixed to `tradepilot.contracts`; subprocess arguments are
  constructed internally and `shell` is disabled.
- Request and response values are checked with the committed JSON schemas.
- Python stdout must contain exactly one JSON response. Diagnostics are bounded
  and are never returned through typed errors.
- The child environment is allowlisted and excludes backend credentials such as
  `DATABASE_URL`.

## Process controls

- stdin: one JSON value plus one newline, maximum 65,536 bytes by default
- stdout: 1 MiB maximum by default
- stderr: 16 KiB maximum by default
- timeout: 10 seconds by default
- concurrency: two Python children by default
- timeout or stream overflow: terminate the child process tree

All limits are positive, validated environment settings. Windows uses
`taskkill /T /F` for descendant termination; POSIX launches a detached process
group and signals the group.

## Failure mapping

Python contract errors retain their stable code and retryable flag, while the
Node-facing message is intentionally generic. Invalid requests, invalid
responses, timeouts, subprocess failures, and protocol failures are typed
separately. Local paths, credentials, stderr, and Python stack traces are not
included.

## Verification

```powershell
cd server
npm run typecheck
npm test
npm run build

cd ..\research
python -m unittest discover -s tests -v
```

Tests cover valid and missing artifacts, Parquet corruption, invalid and
oversized messages, malformed and oversized stdout, timeout, subprocess
failure, and concurrency serialization.

## Limitations

- The adapter is internal and has no HTTP or job-queue integration.
- Artifact verification is one Python process per request.
- Process-tree termination depends on host process facilities and permissions.
- There is no automatic PostgreSQL catalog insertion.
