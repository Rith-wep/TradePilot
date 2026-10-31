# Phase 5, Step 10: Durable Research Job Queue Foundation

Status: complete. Committed as `1cb34b3`.

## Scope

This step adds a PostgreSQL-backed, authenticated research-job lifecycle. It
does not invoke Python, calculate research, publish artifacts, or create
placeholder results.

## State machine

```text
SUBMITTED -> QUEUED -> RUNNING -> SUCCEEDED
                         |
                         +-> QUEUED  (retryable failure; attempts remain)
                         +-> FAILED  (permanent failure or attempts exhausted)

expired RUNNING lease -> recovered claim with a new lease token
```

`CANCELLED` is reserved by the schema for a future authorized cancellation
operation; no cancellation endpoint exists. Every transition is persisted in
`research_job_events`. Completion and failure require the current lease token,
so a crashed or stale worker cannot finalize a recovered job.

## Controls

- Versioned strict contract and unknown-field rejection.
- Allowlisted instruments, timeframe, strategies, and versions.
- Verified dataset foreign key plus provenance matching before insertion.
- Per-owner idempotency with conflict detection.
- Transactional per-owner active and global queue-depth limits.
- `FOR UPDATE SKIP LOCKED` claims, expiring leases, bounded attempts, and
  sanitized error codes.
- Researcher/admin submission and owner-or-admin reads.

## Operations

```powershell
cd server
docker compose up -d postgres
npm run db:migrate
npm run build
npm run worker
```

Queue controls are configured through the `RESEARCH_JOB_*` variables in
`server/.env.example`. The Step 10 worker has no approved research processor.
If started, claimed jobs follow bounded retry/failure with `PROCESSOR_FAILURE`;
it never invents a result.

## Limitations

PostgreSQL is the queue authority. A worker crash leaves a RUNNING job leased;
after expiry another worker can recover it. The worker currently has no lease
heartbeat, cancellation API, dead-letter table, metrics exporter, notification
mechanism, or Python executor. Queue limits are operational safeguards, not
billing quotas. Trusted execution and artifact publication require later
approval.
