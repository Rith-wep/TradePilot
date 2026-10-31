# Phase 5, Step 11: Controlled Python Research Execution

Status: implemented, pending review and commit.

## Execution flow

```text
verified queued job
  -> PostgreSQL SKIP LOCKED claim + fencing lease
  -> fixed, bounded Python execution contract
  -> dataset integrity verification
  -> unchanged indicator/strategy/report workflow
  -> atomic immutable report publication
  -> Python report verification
  -> independent Node/Python artifact verification
  -> transactional catalog registration
  -> fenced SUCCEEDED transition with registered report ID
```

The worker renews its lease while Python runs. Renewal and terminal transitions
require the current lease token and a non-expired lease. A stale worker cannot
complete a recovered job. A failed renewal or fenced terminal transition is a
normal lost-lease outcome: the worker abandons that attempt without terminating
its polling loop.

## Recovery

Report identity excludes run creation metadata. If a worker crashes after
publication or registration, an expired lease is reclaimed and the same inputs
regenerate the same report ID. Atomic storage reuses the valid report, catalog
registration is idempotent, and only the current worker can complete the job.

Retryable failures include bounded subprocess startup, timeout, storage I/O,
and transient catalog/database failures. Invalid contracts, unsupported inputs,
corrupt datasets or reports, provenance conflicts, and malformed subprocess
responses are permanent. Persisted errors are sanitized codes.

Each job also pins the trusted implementation revision at submission. A worker
whose runtime revision differs rejects the job permanently instead of silently
executing a retry with changed code. Operators should inject the build Git SHA
through `TRADEPILOT_IMPLEMENTATION_REVISION`; `unknown` remains the documented
fallback for environments where Git metadata is unavailable.

## Supported scope

- EURUSD and GBPUSD H1 verified snapshots.
- Existing default Price Range Breakout v1 configuration.
- Existing default EMA/RSI Trend Pullback v1 configuration.
- Zero-candidate reports are valid.

No user strategy parameters, live data, broker orders, profitability claims,
or direct HTTP-to-Python execution are supported.

## Operations and limitations

Run migrations, API, and worker as separate processes:

```powershell
cd server
npm run db:migrate
npm run build
npm start
npm run worker
```

The worker currently processes one claimed job at a time per process. It has no
distributed tracing, cancellation, progress percentages, dead-letter workflow,
or resource sandbox beyond process/time/output/environment bounds. Filesystem
and database least privilege, OS isolation, monitoring, and capacity planning
remain deployment responsibilities.
