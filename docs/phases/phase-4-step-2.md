# Phase 4, Step 2: Real-Data Verification and Research Readiness

**Status:** Complete
**Scope:** Credential-gated OANDA verification, bounded H1 ingestion, immutable
quality evidence, and candidate-report pipeline compatibility. No formula changes.

## Flow

```text
environment credentials
  -> EURUSD/GBPUSD connectivity probes
  -> bounded completed-H1 ingestion
  -> immutable snapshot and checksum verification
  -> coverage/session-gap/spread/revision audit
  -> READY or FAILED
  -> unchanged indicators and strategies
  -> immutable reproducible candidate reports
  -> content-addressed readiness report
```

The command never uses mock or synthetic prices as a fallback. Missing
credentials, failed connectivity, invalid checksums, insufficient coverage,
unexpected open-session gaps, incompatible data, and unapproved revisions fail
closed.

## Command

```powershell
cd research
$env:OANDA_API_TOKEN = "..."
$env:OANDA_ACCOUNT_ID = "..."

tradepilot-oanda-readiness connectivity --environment practice

tradepilot-oanda-readiness run `
  --start 2024-01-01T00:00:00Z `
  --end 2024-01-29T00:00:00Z `
  --environment practice `
  --data-output data `
  --report-output reports `
  --readiness-output readiness-reports
```

Ranges are UTC-hour aligned, completed, and limited to 31 days by default.
Both EUR/USD and GBP/USD must pass connectivity independently.

## Readiness policy

The default policy requires at least 200 stored candles, 99% expected-session
coverage, valid OANDA H1 provenance, non-synthetic records, valid immutable
checksums, and no unexpected open-session gaps. The OANDA calendar uses the
common Sunday 17:00 through Friday 17:00 America/New_York week so DST conversion
is explicit. Holiday closures are not inferred automatically.

Spread evidence records minimum, median, 95th percentile, maximum, and the
number above the 20-pip audit threshold. Unusual spreads are reported and kept;
invalid negative spreads remain validation errors.

## Historical revisions

Re-ingestion rejects conflicting historical candles by default and leaves the
previous latest snapshot unchanged. `--approve-revisions` is required to
publish a revised content-addressed snapshot. The previous snapshot remains
immutable, while the readiness report records previous/current dataset IDs,
revision count, approval state, and changed timestamps.

## Pipeline evidence

Only a quality-ready snapshot enters the existing pipeline. The unchanged
default breakout and EMA/RSI pullback implementations generate candidate
reports using existing indicators and provenance checks. Zero-candidate reports
are valid. Each report is generated twice and must retain the same deterministic
identity; the stored report is independently verified.

No win rate, P&amp;L interpretation, parameter tuning, or profitability claim is
produced.

## Evidence storage

Readiness content uses exact Decimal values, UTC timestamps, canonical JSON,
and SHA-256 identity. Reports are published to
`readiness-reports/{report-id}/readiness.json` without overwriting existing
content. Creation time and credentials do not enter deterministic identity.

## Tests

Default CI uses synthetic provider-shaped data and local immutable snapshots.
The existing OANDA practice smoke test remains opt-in through
`TRADEPILOT_RUN_OANDA_SMOKE=1` and requires user-supplied credentials.

## Limitations

- Real API behavior remains unverified until the credential-gated smoke and
  readiness commands succeed for the user's OANDA region/account.
- The default calendar has no automatic OANDA holiday/maintenance feed.
- A 31-day verification window is a readiness sample, not long-term market
  coverage.
- Spread statistics describe aggregated H1 bid/ask candles, not executable
  tick liquidity.
- Explicit revision approval confirms acceptance; it does not establish why a
  provider revised history.
- OANDA licensing restricts redistribution of downloaded data.

## Next step

Stop here and wait for approval before Phase 4, Step 3.
