# Phase 1, Step 2: Provider Adapter and Historical Ingestion

**Status:** Complete  
**Scope:** Provider abstraction, mock ingestion, normalization, retries,
validation, and local Parquet storage.

## Goal

Build a maintainable pipeline that can request historical candles from a market
data provider, normalize them into the existing canonical model, validate them,
and save research datasets locally. No live provider was selected or claimed to
work during this step.

## What was implemented

- A `MarketDataProvider` protocol accepting instrument, timeframe, UTC date
  range, timeout, and pagination cursor.
- Provider-neutral request, page, raw-candle, and typed error contracts.
- A deterministic mock provider with pagination and configurable temporary
  failures.
- Normalization that:
  - treats provider timestamps as candle-open times;
  - converts aware timestamps to UTC;
  - parses exact decimal prices;
  - rejects incomplete candles, naive timestamps, invalid decimals, and
    non-finite values; and
  - requires real bid and ask fields instead of deriving them from midpoint
    prices.
- Historical ingestion with bounded date batches, cursor pagination, request
  timeouts, exponential retries, rate-limit support, range enforcement, and
  duplicate handling.
- Validation before persistence using the Step 1 validator.
- Atomic Parquet persistence organized by provider, instrument, and timeframe.
- A JSON manifest containing provenance, retrieval range, retrieval time,
  schema version, price basis, quality results, and SHA-256 checksums.
- Safe repeated ingestion: identical records are deduplicated and conflicting
  records at an existing timestamp are rejected.
- A reproducible synthetic mock-ingestion CLI.
- Expanded automated test coverage.

## Architecture

```text
MarketDataProvider
        |
        v
batched and paginated retrieval
        |
        v
retry / timeout handling
        |
        v
UTC bid/ask normalization
        |
        v
deduplication and validation
        |
        v
Parquet dataset + JSON manifest
```

The requested date range is half-open: `[start, end)`. Provider-specific HTTP
and authentication code stays separate from normalization and storage.

## Storage layout

```text
research/data/{provider}/{instrument}/{timeframe}/candles.parquet
research/data/{provider}/{instrument}/{timeframe}/manifest.json
```

The generated `research/data/` directory is ignored by Git. The ignore rule is
anchored as `/data/` so it does not hide the source package named `data`.

## Main files

```text
research/src/tradepilot/data/providers/base.py
research/src/tradepilot/data/providers/mock.py
research/src/tradepilot/data/normalization.py
research/src/tradepilot/data/ingestion.py
research/src/tradepilot/data/storage.py
research/src/tradepilot/data/ingestion_cli.py
research/tests/ingestion_helpers.py
research/tests/test_normalization.py
research/tests/test_ingestion.py
research/tests/test_storage.py
research/tests/test_ingestion_cli.py
research/pyproject.toml
research/README.md
research/.gitignore
```

## Commands

From `research/`:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e .

tradepilot-ingest-mock `
  --input fixtures/synthetic_eurusd_h1.csv `
  --output data

python -m unittest discover -s tests -v
```

## Verification result

The final suite retained all Step 1 tests and added Step 2 coverage.

```text
Ran 27 tests in 0.198s
OK

TEST_EXIT=0
VALIDATE_EXIT=0
```

The generated artifact was also read back and inspected:

```text
Parquet magic bytes: PAR1
Parquet rows: 5
Manifest rows: 5
Price basis: bid_ask
Dataset SHA-256 length: 64
```

Tests cover successful pagination, malformed provider data, duplicate candles,
missing intervals, UTC conversion, bid/ask consistency, repeat ingestion,
conflicting stored records, timeouts, permanent errors, and retry limits.

## Provider research decision

OANDA v20 is the leading candidate because its official documentation describes
H1 candles, bid and ask components, completion flags, candle-open timestamps,
and paginated historical access. It requires a compatible account, token, and
license acceptance.

Dukascopy offers historical bid/ask export, but a stable automated API contract
and commercial redistribution permissions were not established during this
step.

No live adapter or real market dataset was added.

## Limitations

- Only the deterministic mock provider is implemented.
- No provider credentials or live requests have been tested.
- Licensing, storage, and redistribution rights require confirmation before a
  commercial provider is integrated.
- Missing intervals are warnings but are not yet classified with a forex market
  calendar.
- The example CLI uses synthetic EUR/USD H1 data.

## Next step

Obtain approval for a real provider and confirm its licensing and account-region
requirements before implementing or testing a live adapter. Do not begin
strategies or later roadmap phases without explicit approval.

