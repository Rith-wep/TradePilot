# Trusted research execution contract v1

The worker sends exactly one JSON request over stdin to the fixed Python module
`tradepilot.execution`. Stdout must contain exactly one JSON response. The
subprocess uses `shell: false`, bounded input/output/error streams, a timeout,
bounded concurrency, process-tree termination, and a sanitized environment.

The request contract is `tradepilot-research-execution/v1` and contains only a
request ID, verified dataset ID, EURUSD/GBPUSD, H1, one allowlisted strategy
name, and the job's pinned implementation revision. The revision is either a
40-character lowercase Git SHA or the explicit fallback `unknown`. Paths,
commands, executables, and parameters are not accepted. JSON schemas are
committed under `research/contracts/`.

`price_range_breakout` selects the existing `BreakoutConfig()` defaults;
`ema_rsi_trend_pullback` selects the existing `PullbackConfig()` defaults. Both
map to the unchanged Python strategy implementation version `1.0.0`. The session
calendar is the existing default `WeeklySessionCalendar`.

Python resolves the dataset only beneath the approved dataset root, requires a
unique matching snapshot, verifies its immutable identity and checksums, calls
`tradepilot.workflows.research_run`, and publishes through `ReportStorage`.
Publication is staged and atomic. The published report is verified before its
ID is returned. Creation time stays outside deterministic identity.

Node then uses the independent artifact verifier and trusted catalog registrar.
Only after verified, idempotent registration does the current lease holder set
the job to `SUCCEEDED` with the report ID.

The API pins the trusted server revision when the job is created. Before
execution, a worker compares that pin with its own trusted runtime revision and
fails permanently on a mismatch. This prevents a retry after deployment from
silently running different code. Git is optional: deployments without a
discoverable SHA use `unknown`, which is explicit but provides weaker revision
provenance and should be replaced by `TRADEPILOT_IMPLEMENTATION_REVISION` in
production.

