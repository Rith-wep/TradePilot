# Phase 4: Dukascopy Paired CSV Import

**Status:** Complete

## Supported input

The offline importer accepts separate EUR/USD H1 BID and ASK files with the
exact header:

```text
Etc/UTC,Open,High,Low,Close,Volume
```

The inspected source files use timestamps such as
`2026-09-01T00:00:00+00:00`. The matching explicit Python format is:

```text
%Y-%m-%dT%H:%M:%S%z
```

The format remains a required command argument and is never inferred.

## Import command

```powershell
cd research

$bidHash = (Get-FileHash ..\EUR-USD_1Hour_BID_2026-09-01_to_2026-09-29_Etc_UTC.csv -Algorithm SHA256).Hash.ToLower()
$askHash = (Get-FileHash ..\EUR-USD_1Hour_ASK_2026-09-01_to_2026-09-29_Etc_UTC.csv -Algorithm SHA256).Hash.ToLower()

python -m tradepilot.data.dukascopy_csv_cli `
  --instrument EURUSD `
  --bid ..\EUR-USD_1Hour_BID_2026-09-01_to_2026-09-29_Etc_UTC.csv `
  --ask ..\EUR-USD_1Hour_ASK_2026-09-01_to_2026-09-29_Etc_UTC.csv `
  --timestamp-format "%Y-%m-%dT%H:%M:%S%z" `
  --expected-bid-sha256 $bidHash `
  --expected-ask-sha256 $askHash `
  --strict-gaps `
  --output data
```

When installed, `tradepilot-import-dukascopy` provides the same command.

## Validation

Each side is parsed independently. Headers, explicit UTC timestamps, H1
alignment, chronological order, uniqueness, finite Decimal OHLC, and
non-negative finite volume are required. BID and ASK timestamp sets must match
exactly. No missing side or missing interval is created, copied, interpolated,
or forward-filled.

The combined candles pass through the existing provider-neutral normalization
and validators. Invalid OHLC relationships and BID above ASK are errors.
Unusual spreads remain warnings and valid candles are retained.

The New York FX calendar classifies expected closures and unexpected missing
open-session candles. `--strict-gaps` exits before snapshot publication when an
unexpected gap exists.

## Provenance and storage

Both raw files are SHA-256 hashed before parsing. Optional expected hashes fail
closed on mismatch. Retrieval provenance records hashes, basenames, sizes, row
counts, delimiter, timestamp format, timestamp convention, adapter version, and
the fact that volume is validated but not stored.

The hash pair determines `dataset_version`. Existing immutable Parquet
snapshots, canonical dataset IDs, checksums, manifests, integrity verification,
and retrieval records are reused. Repeated identical imports reuse content.
Historical conflicts fail unless `--approve-revisions` is explicit; previous
snapshots remain immutable.

## Output

The JSON result contains source hashes, dataset ID, canonical and Parquet
checksums, date coverage, expected and unexpected gaps, spread distribution,
duplicate and revision counts, and snapshot paths.

## Tests and data policy

Committed fixtures contain synthetic values in the Dukascopy CSV shape. Actual
Dukascopy exports remain outside Git. The repository ignores the inspected
root-level EUR/USD BID and ASK filenames.

## Limitations

- EUR/USD H1 only; GBP/USD is intentionally deferred.
- Volume is validated but the canonical candle schema does not store it.
- The calendar has no automatic holiday or broker-maintenance feed.
- Coverage and spread results describe the supplied files, not all Dukascopy
  history or executable tick liquidity.
- Source-data licensing and redistribution restrictions still apply.
- The importer assumes timestamps denote candle openings, matching the
  inspected export and the TradePilot canonical convention.
