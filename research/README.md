# TradePilot research workspace

This Phase 1 workspace defines the market-data contract, validates a small
explicitly synthetic EUR/USD H1 bid/ask fixture, and provides a provider-neutral
historical ingestion pipeline with Parquet storage. It contains no trading
strategies, backtesting, live provider adapter, or execution logic.

## Requirements

- Python 3.12 or newer
- Apache Arrow for Parquet support and, on Windows, the IANA timezone database
  used to materialize Arrow's UTC timestamps (installed by the package)

## Setup

From `research/`, create and activate a virtual environment, then install the
package locally:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e .
```

No vendor credentials are required. Runtime dependencies are `pyarrow` plus
`tzdata` on Windows.

## Validate the synthetic fixture

```powershell
tradepilot-validate fixtures/synthetic_eurusd_h1.csv
```

Alternatively, without installing the package:

```powershell
$env:PYTHONPATH = "src"
python -m tradepilot fixtures/synthetic_eurusd_h1.csv
```

The command writes a deterministic JSON quality report. It exits with status
`0` when there are no validation errors and status `1` when errors are found.
CSV parse or file errors exit with status `2`.

## Provider architecture

`MarketDataProvider` is a small protocol that accepts an instrument, timeframe,
UTC start/end range, request timeout, and optional pagination cursor. Adapters
return untrusted `ProviderCandle` pages. The ingestion service then:

1. divides the half-open request range `[start, end)` into bounded batches;
2. follows provider pagination cursors;
3. retries timeouts, rate limits, and explicitly transient provider failures
   with bounded exponential backoff;
4. converts timezone-aware candle-open timestamps to UTC and parses prices as
   decimals;
5. rejects incomplete records and requires both bid and ask OHLC values;
6. deduplicates identical timestamps, rejects conflicting duplicates, and runs
   the existing quality validator before saving; and
7. atomically writes a merged, sorted Parquet dataset and JSON manifest.

Provider-specific HTTP, authentication, response parsing, rate-limit behavior,
and licensing remain isolated from normalization, validation, and storage.

### Real provider research and configuration

No live adapter is enabled or claimed to work in this phase. OANDA v20 is the
leading candidate because its official API documents separate bid and ask
candles (`price=BA`), H1 granularity, candle-open timestamps, completion flags,
and a maximum of 5,000 candles per response. Its official getting-started guide
states that access requires a compatible v20 account, personal token, and API
license acceptance, with historical pricing advertised back to 2005:

- https://developer.oanda.com/rest-live-v20/instrument-ep/
- https://developer.oanda.com/rest-live-v20/instrument-df/
- https://developer.oanda.com/rest-live-v20/introduction/

Before implementing it, confirm account-region availability and obtain written
clarity on storage, commercial use, and redistribution. An eventual adapter
would read credentials from environment variables (never source control), use
the documented regional base URL, request unsmoothed completed `BA` H1 candles,
and map HTTP 429/5xx/timeouts to the typed transient errors.

Dukascopy's official historical export also advertises bid/ask data, but no
stable automated HTTP contract or redistribution permission has been adopted:

- https://www.dukascopy.com/api/data/get/historical-data-export

## Run deterministic mock ingestion

The mock command passes the existing synthetic fixture through pagination,
normalization, validation, deduplication, and Parquet storage:

```powershell
tradepilot-ingest-mock --input fixtures/synthetic_eurusd_h1.csv --output data
```

Or without installing an editable package:

```powershell
$env:PYTHONPATH = "src"
python -m tradepilot.data.ingestion_cli --input fixtures/synthetic_eurusd_h1.csv --output data
```

The command is synthetic-only and performs no network calls.

## Storage format

Datasets use this layout:

```text
data/{provider}/{instrument}/{timeframe}/candles.parquet
data/{provider}/{instrument}/{timeframe}/manifest.json
```

Parquet stores UTC candle-open timestamps, symbol, timeframe, exact decimal
bid/ask OHLC, source, provider dataset version, and the synthetic-data flag. The
manifest records the schema version, requested range, retrieval timestamp,
price basis, provider metadata, row count, quality report, a canonical dataset
SHA-256, and the Parquet file SHA-256. Re-ingesting identical records does not
duplicate rows; a different record at an existing timestamp is rejected rather
than silently overwritten. Generated `data/` is git-ignored.

## Run tests

The tests use Python's standard-library test runner:

```powershell
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -v
```

## Data conventions

- Each timestamp is the candle-open time, ISO 8601, UTC-aware, and aligned to
  the start of an hour.
- Prices use decimal arithmetic; no binary floating-point conversion occurs.
- Each candle contains bid and ask OHLC values, with bid prices no greater than
  the corresponding ask prices.
- Gaps are reported as warnings rather than filled because weekends, holidays,
  or source outages require provenance-aware interpretation.
- The included fixture is synthetic and must not be represented as market data.

## Current limitations

- There is no live HTTP adapter and no real or proprietary dataset is included.
- Only canonical bid/ask candles are accepted; midpoint-only data is rejected
  rather than converted into artificial bid/ask prices.
- A gap is a quality warning, not proof of missing provider data, because FX
  weekends and holidays need a market-calendar-aware classifier in later work.
- The initial CLI fixture and instrument metadata cover EUR/USD H1 only; the
  provider-neutral Python interfaces can accept other instrument metadata.
- Provider timeout enforcement belongs to each future network adapter; the
  ingestion layer retries surfaced `TimeoutError` instances.

