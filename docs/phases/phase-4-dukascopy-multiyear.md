# Phase 4 — Dukascopy multi-year batch import

## Scope

This milestone imports an ordered collection of monthly Dukascopy H1 BID/ASK
CSV pairs into one immutable EURUSD or GBPUSD snapshot. It does not change
indicators, strategy rules, execution, accounting, or the OANDA adapter.

## Batch plan

The command accepts a JSON plan. Paths are relative to the plan file unless
absolute. Every monthly entry must provide the expected SHA-256 for both source
files. Months must be unique, ordered, and contiguous.

```json
{
  "schema_version": "tradepilot-dukascopy-batch-plan/v1",
  "instrument": "EURUSD",
  "timeframe": "H1",
  "timestamp_format": "%Y-%m-%d %H:%M:%S",
  "delimiter": ",",
  "calendar": {
    "name": "approved-dukascopy-calendar",
    "timezone": "UTC",
    "open_weekday": 6,
    "open_time": "22:00",
    "close_weekday": 4,
    "close_time": "22:00",
    "closure_dates": []
  },
  "months": [
    {
      "month": "2023-01",
      "bid_path": "raw/EURUSD-2023-01-BID.csv",
      "ask_path": "raw/EURUSD-2023-01-ASK.csv",
      "bid_sha256": "<64 lowercase hex characters>",
      "ask_sha256": "<64 lowercase hex characters>"
    }
  ]
}
```

The timestamp format is always explicit. The importer does not infer a format,
timezone, holiday calendar, or broker session. Raw market files and credentials
must remain outside Git.

A non-runnable two-adjacent-month template is provided at
`research/fixtures/dukascopy/eurusd-two-adjacent-months.plan.example.json`.
Its file paths and hash strings are placeholders by design. Replace them only
after obtaining complete monthly exports and calculating their actual hashes.
Review and approve the calendar, including holiday closures, before import.

## Validation and publication

Before writing anything, the importer verifies every source hash, header,
volume, timestamp, month boundary, ordering, duplicate, BID/ASK alignment,
Decimal OHLC constraint, spread relationship, overlap, and configured-session
gap. Missing open-session candles fail closed; candles are never fabricated.

After all months pass, their canonical candles are consolidated once. The
complete Parquet file, source-artifact manifest, and dataset manifest are staged
in a private sibling directory and published as one content-addressed snapshot
with an atomic directory rename. Existing historical candles cannot change
unless `--approve-revisions` is supplied. Approval creates a new immutable
snapshot and preserves the old one.

The source-artifact manifest records file name, side, declared month, SHA-256,
byte count, row count, and first/last UTC timestamp. Its checksum participates
in the dataset identity, so identical candle content from different declared
source artifacts is distinguishable. Legacy OANDA and single-file snapshots do
not require this optional manifest and retain their existing identities.

Monthly and yearly quality reports include expected/observed candle counts,
coverage, gaps, duplicates, overlaps, and Decimal spread minimum, median, 95th
percentile, and maximum. Quality reports are content addressed.

## Command

```powershell
cd research
python -m pip install -e .
tradepilot-import-dukascopy-batch path\to\plan.json --output data
```

Only after reviewing a detected revision:

```powershell
tradepilot-import-dukascopy-batch path\to\plan.json --output data --approve-revisions
```

The output includes the dataset ID and checksums, artifact checksum, quality
report ID, revision count, and a deterministic 60/20/20 partition plan ID.

## Locked-test governance

The 60/20/20 boundaries are candle-count based, chronological, half-open, and
bound to the exact dataset ID. The CLI publishes a persistent immutable
`sealed-partitions.json` below the dataset namespace. This solves the earlier
process-local sealing problem: another process can verify the same plan and
cannot silently replace it.

The record is deliberately `SEALED` with `locked_test_evaluated=false`. This
milestone provides no command to authorize, unlock, inspect, or evaluate the
test partition. A future explicit governance milestone must define durable
authorization and one-time evaluation semantics.

## Tests

```powershell
cd research
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -v
```

Offline tests generate small synthetic monthly BID/ASK files for both EURUSD
and GBPUSD. No proprietary data is committed.

## Limitations

- Session and holiday accuracy depends entirely on the approved plan calendar.
- Strict mode rejects any unexplained open-session gap; no automatic holiday
  discovery or gap waiver exists.
- Atomic directory publication assumes staging and destination share a
  filesystem and that the filesystem implements atomic rename semantics.
- Source hashes prove byte identity, not Dukascopy licensing or authenticity.
- Spread statistics flag distribution extremes but do not decide whether a
  market observation is economically acceptable.
- Partition sealing is cross-process integrity protection, not authorization
  to evaluate the locked test period.
