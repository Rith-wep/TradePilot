# Phase 2, Step 3: Signal Validation and Reproducible Research Reports

**Status:** Complete  
**Scope:** Immutable candidate-signal reports, canonical identity, validation,
storage, generation, and verification. No performance calculations.

## Goal

Turn candidate setups into trustworthy research artifacts before building a
backtesting engine. Reports preserve what data, configuration, code revision,
rules, and timestamps produced each candidate.

## Architecture

```text
integrity-verified immutable dataset
              |
              v
existing indicators + strategy detector
              |
              v
immutable SetupRecord candidates
              |
              v
research provenance and timestamp validation
              |
              v
canonical deterministic JSON content
              |
              +---- SHA-256 ----> report ID
              |
              v
staged atomic immutable report publication
```

The reporting package accepts setup records and contains no strategy-specific
detection formulas.

## Deterministic content

Each report records:

- report schema version;
- dataset ID and canonical checksum;
- instrument, timeframe, and dataset range;
- strategy name, version, configuration, and fingerprint;
- indicator parameters and price basis;
- session calendar and unexpected-gap policy;
- research engine version;
- implementation revision;
- immutable candidate signals and evidence.

Each signal repeats dataset provenance and preserves its opening timestamp,
observable timestamp, direction, rule evidence, indicator values, invalidation
conditions, and non-executable structural invalidation reference.

Run `created_at` metadata is stored separately and excluded from content
identity, so repeated runs at different times reuse the same report ID.

## Canonical serialization and identity

Canonical JSON uses UTF-8, sorted keys, compact separators, UTC `Z` timestamps,
stable enum strings, and exact base-10 Decimal strings. NaN and Infinity are
rejected.

```text
report ID = SHA-256(canonical deterministic report content)
```

Implementation revision is included in identity. This provides stronger
provenance because known code revisions cannot silently share a report ID. The
tradeoff is that an unrelated commit change produces a new report ID. Revision
resolution order is:

1. `TRADEPILOT_IMPLEMENTATION_REVISION` environment override;
2. `git rev-parse HEAD` when available;
3. documented `unknown` fallback.

Git is optional. `unknown` keeps research functional but cannot distinguish
different unavailable or uncommitted implementations.

## Research validation

For H1 signals:

```text
observable_at = detection_candle_open_time + 1 hour
```

The detection opening timestamp must exactly exist among the selected verified
dataset's candle timestamps. Being merely inside the dataset range is not
sufficient. All signal timestamps must be UTC.

Strategy, version, fingerprint, instrument, timeframe, dataset ID/checksum, and
signal provenance must agree. Duplicate candidate identities are rejected.
Signals are sorted chronologically. A report containing zero signals is valid.

## Storage and concurrency

```text
reports/{report-id}/report.json
reports/{report-id}/runs/{run-metadata-id}.json
```

A complete report directory, including first-run metadata, is written under a
private staging name on the same filesystem. Only then is it published with a
directory rename. Concurrent identical writers either publish first or verify
and reuse the valid winner. Existing immutable report content is never
overwritten. Incomplete or corrupt published destinations are rejected.

Run metadata is content-addressed separately, allowing multiple creation times
without changing the report.

Assumptions and limitations:

- same-filesystem directory rename must be atomic;
- hard links are used for race-safe metadata publication;
- local filesystems are the supported baseline;
- network and unusual filesystems may offer weaker semantics;
- an operating-system crash may leave private `.staging-*` directories, but
  they are never treated as published reports.

## Commands

```powershell
cd research
python -m pip install -e .
python -m unittest discover -s tests -v

tradepilot-research-report generate `
  data/mock/EURUSD/H1 breakout `
  --output reports --lookback 20

tradepilot-research-report generate `
  data/mock/EURUSD/H1 pullback `
  --output reports `
  --ema-period 200 --rsi-period 14 --atr-period 14

tradepilot-research-report verify reports/{report-id}
```

## Main files

```text
research/src/tradepilot/reporting/__init__.py
research/src/tradepilot/reporting/models.py
research/src/tradepilot/reporting/canonical.py
research/src/tradepilot/reporting/validation.py
research/src/tradepilot/reporting/storage.py
research/src/tradepilot/reporting/cli.py
research/tests/reporting_helpers.py
research/tests/test_research_report.py
research/tests/test_report_storage.py
research/tests/test_report_cli.py
```

## Verification results

The complete research test suite was run after implementation:

```text
Ran 97 tests in 1.042s
OK
```

An end-to-end synthetic run generated this deterministic result:

```text
dataset_id: 2c1c4912848274db1d0fd296a76c796d27caa3f3a14d3df1b1a51fc60e3c8cf9
report_id: 8b2fbcbe1a5854d7b7e1e3ebe4991f1833db82aad3088a08e7354a374bd07821
signal_count: 1
implementation_revision: verification-revision
first generation reused: false
second generation reused: true
independent verification: valid
```

The explicit revision value above makes this example reproducible independent
of the current Git checkout. With no environment override, the engine uses the
current Git commit SHA when available and otherwise records `unknown`.

## Report shape

The stored `report.json` uses this structure (values shortened for readability):

```json
{
  "report_id": "8b2fbcbe...",
  "content": {
    "dataset_id": "2c1c4912...",
    "dataset_checksum": "9df51f55...",
    "strategy_name": "price_range_breakout",
    "strategy_version": "1",
    "configuration_fingerprint": "...",
    "research_engine_version": "1",
    "implementation_revision": "verification-revision",
    "signals": [
      {
        "dataset_id": "2c1c4912...",
        "dataset_checksum": "9df51f55...",
        "setup": {
          "detection_candle_open_time": "2024-01-02T03:00:00Z",
          "observable_at": "2024-01-02T04:00:00Z",
          "direction": "SHORT",
          "rule_evidence": [],
          "structural_invalidation_reference": "1.100275"
        }
      }
    ]
  }
}
```

Decimal-bearing fields are encoded as strings in canonical JSON, so their exact
base-10 representation is retained.

## Limitations

- Reports contain candidates, not outcomes or performance statistics.
- Independent verification checks internal content integrity; it does not
  re-download provider data.
- Only H1 observability duration is implemented.
- The `unknown` revision fallback weakens code-level distinction.
- Published reports are immutable; repair means regenerating from source inputs.
- No signing authority or cryptographic signature is implemented beyond SHA-256
  content addressing.

## Next step

Review report identity, provenance, and filesystem assumptions. Do not begin the
backtesting engine without explicit approval.
