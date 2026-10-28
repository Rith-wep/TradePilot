# Phase 1, Step 3: Historical Dataset Integrity and Reproducibility

**Status:** Complete  
**Scope:** Session-aware gaps, immutable dataset snapshots, integrity checks,
revision detection, and dataset audit tooling.

## Goal

Make synthetic historical datasets reproducible and independently auditable
before connecting a live market-data provider. This step does not add market
indicators, strategies, backtesting, APIs, UI, or AI.

## What was implemented

- A configurable weekly trading-session calendar.
- Gap classification that distinguishes expected closures from unexpected
  missing H1 candles without fabricating data.
- Explicit local-date closures for provider-specific holidays or maintenance.
- Content-addressed immutable Parquet snapshots.
- Deterministic dataset identifiers based on canonical schema information and
  sorted candle content.
- Separate retrieval records so provider metadata and retrieval timestamps do
  not change the dataset identity.
- Controlled historical revisions that create new snapshots and identify every
  changed timestamp.
- Snapshot comparison using per-candle content checksums.
- Independent verification of:
  - required files;
  - Parquet SHA-256;
  - canonical dataset SHA-256;
  - dataset ID;
  - Parquet schema;
  - manifest row count and timestamp range;
  - stored quality report;
  - dataset index consistency; and
  - canonical candle validation.
- A `tradepilot-audit` JSON CLI with nonzero integrity-failure exit status.

## Architecture

```text
provider-neutral ingestion
          |
          v
canonical candles + validation
          |
          v
schema + content hash = dataset ID
          |
          v
immutable Parquet snapshot + manifest
          |
          +------> separate retrieval records
          |
          v
integrity verifier + session-aware audit CLI
```

## Storage layout

```text
data/{provider}/{instrument}/{timeframe}/
|-- index.json
|-- retrievals/
|   `-- {retrieval-id}.json
`-- snapshots/
    `-- {dataset-id}/
        |-- candles.parquet
        `-- manifest.json
```

Snapshots are never overwritten. `index.json` identifies the latest snapshot.
An identical ingestion reuses its existing snapshot and records retrieval
metadata separately.

## Session model

The default calendar represents a common FX schedule:

```text
Open:  Sunday 22:00 UTC
Close: Friday 22:00 UTC
```

This is not assumed to be correct for every broker. The timezone, weekly times,
and full-date closures are configurable. The classifier labels every absent H1
timestamp between stored candles but never inserts a replacement candle.

## Commands

From `research/`:

```powershell
python -m pip install -e .
python -m unittest discover -s tests -v

tradepilot-ingest-mock `
  --input fixtures/synthetic_eurusd_h1.csv `
  --output data

tradepilot-audit data/mock/EURUSD/H1
```

Example custom session:

```powershell
tradepilot-audit data/mock/EURUSD/H1 `
  --timezone UTC `
  --open-weekday 6 --open-time 22:00 `
  --close-weekday 4 --close-time 22:00 `
  --closure-date 2024-12-25
```

## Verification result

Final automated suite:

```text
Ran 42 tests in 0.493s
OK
TEST_EXIT=0
```

End-to-end synthetic ingestion and audit:

```text
Rows: 5
Integrity issues: 0
Dataset ID length: 64
Dataset checksum length: 64
Retrieval records: 1
INGEST_EXIT=0
AUDIT_EXIT=0
```

The tests cover weekend closures, weekday gaps, configurable sessions and
closure dates, immutable snapshots, deterministic identifiers, historical
revisions, corrupt Parquet files, missing files, checksum mismatches,
index/manifest mismatches, CLI reporting, and nonzero failure status.

## Main files

```text
research/src/tradepilot/data/sessions.py
research/src/tradepilot/data/storage.py
research/src/tradepilot/data/integrity.py
research/src/tradepilot/data/audit_cli.py
research/tests/test_sessions.py
research/tests/test_versioning.py
research/tests/test_integrity.py
research/tests/test_audit_cli.py
research/README.md
research/pyproject.toml
```

## Limitations

- Only synthetic data was used.
- The default calendar is a convention, not a universal forex or broker
  calendar.
- Holidays must be supplied explicitly; there is no bundled holiday database.
- H1 is the only supported audit interval in the current product scope.
- A live provider's historical revision policy is not yet defined.
- Corruption is detected but not automatically repaired.

## Next step

Review and approve the completed Phase 1 foundation. A real provider adapter
still requires explicit approval and licensing confirmation. Do not begin
strategies or another roadmap phase without approval.
