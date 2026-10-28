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
7. writes a merged, sorted, immutable Parquet snapshot and JSON manifest.

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

Datasets use content-addressed immutable snapshots:

```text
data/{provider}/{instrument}/{timeframe}/index.json
data/{provider}/{instrument}/{timeframe}/retrievals/{retrieval-id}.json
data/{provider}/{instrument}/{timeframe}/snapshots/{dataset-id}/candles.parquet
data/{provider}/{instrument}/{timeframe}/snapshots/{dataset-id}/manifest.json
```

Parquet stores UTC candle-open timestamps, symbol, timeframe, exact decimal
bid/ask OHLC, source, provider dataset version, and the synthetic-data flag.
The deterministic dataset ID hashes the canonical schema identity and candle
content. Provider metadata, request ranges, and retrieval times are stored in
separate retrieval records and do not change content identity.

Re-ingesting identical content reuses the snapshot. Changed content creates a
new snapshot only when revisions are explicitly allowed; normal ingestion still
rejects conflicting historical candles. The index points to the latest snapshot
without changing older snapshots. Generated `data/` is git-ignored.

## Market-session-aware gaps

`WeeklySessionCalendar` classifies every absent H1 candle-open timestamp as:

- `expected_closure` when the configured market session is closed; or
- `unexpected_missing` when the configured session expects trading.

The default models Sunday 22:00 through Friday 22:00 UTC, but this is only a
starting convention. Timezone, weekly open/close weekday and time, and explicit
full-date closures are configurable. Broker holidays and trading hours must be
supplied for the intended data source. No missing candles are created.

## Audit a stored dataset

```powershell
tradepilot-audit data/mock/EURUSD/H1
```

Audit a dataset with a provider-specific session and explicit closure date:

```powershell
tradepilot-audit data/mock/EURUSD/H1 `
  --timezone UTC `
  --open-weekday 6 --open-time 22:00 `
  --close-weekday 4 --close-time 22:00 `
  --closure-date 2024-12-25
```

The JSON audit shows provider, instrument, timeframe, date range, row count,
dataset ID, checksums, validation issues, and classified missing intervals. It
independently verifies the Parquet checksum, canonical content checksum,
content-derived ID, schema, manifest values, index consistency, and canonical
candle validation. Exit status is `0` for valid integrity, `1` for integrity or
validation failure, and `2` for invalid calendar arguments.

## Technical indicator engine

The pure `tradepilot.indicators` package calculates indicators from validated,
completed canonical candles. It does not import provider, storage, strategy, or
execution code.

### Conventions

- **EMA:** selected close price; the first value is the simple average of the
  first `period` closes. Later values use `alpha = 2 / (period + 1)`.
- **RSI:** selected close price and Wilder smoothing. The first value uses the
  average gains and losses from the first `period` close changes, requiring
  `period + 1` candles. Later averages use Wilder's recursive formula. RSI is
  100 when average loss is zero and gain is positive; it is 50 when both are
  zero.
- **ATR:** selected high, low, and close. True range is the greatest of
  `high-low`, `abs(high-previous close)`, and `abs(low-previous close)`. The
  first ATR is the average of the first `period` true ranges; later values use
  Wilder smoothing.
- **Warm-up:** unavailable aligned points contain `null`. EMA and ATR need
  `period` candles; RSI needs `period + 1`.
- **Price basis:** `bid`, `ask`, or `mid`. Mid values are arithmetic averages of
  the corresponding bid/ask OHLC fields and are analytical, not executable
  prices. Because bid and ask extrema may occur at different moments, an
  averaged midpoint high/low is an approximation of a true midpoint candle.
- **Missing intervals:** no values are invented. Smoothing continues across the
  observed completed candles; use `tradepilot-audit` to decide whether gaps are
  acceptable for a particular research run.
- **Validation:** periods must be positive integers. Invalid, unordered,
  duplicate, mixed-instrument, or mixed-timeframe candles are rejected.
- **Precision:** calculations use `Decimal` under a fixed 34-digit local
  precision context and do not depend on the caller's decimal context.

Canonical provider normalization rejects incomplete candles. Indicator output
at each timestamp is calculated only from that candle and earlier input
candles. The test suite compares every full-series prefix against a separate
prefix-only calculation to detect future-data leakage.

### Calculate indicators from an immutable snapshot

```powershell
tradepilot-indicators data/mock/EURUSD/H1 `
  --ema-period 3 `
  --rsi-period 3 `
  --atr-period 3 `
  --price-basis mid
```

The command first performs Step 3 integrity verification. It exits with status
`1` for a corrupt dataset and `2` for invalid indicator parameters. Output is
JSON containing the immutable dataset ID and timestamp-aligned series.

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
- Session classification is only as accurate as its configured broker schedule
  and explicit closure dates; there is no built-in global holiday database.
- The initial CLI fixture and instrument metadata cover EUR/USD H1 only; the
  provider-neutral Python interfaces can accept other instrument metadata.
- Provider timeout enforcement belongs to each future network adapter; the
  ingestion layer retries surfaced `TimeoutError` instances.
- Revision snapshots require explicit `allow_revisions=True`; live-provider
  revision policy remains intentionally undecided.
- Indicators currently support canonical H1 candles and return raw Decimal
  precision; display rounding is intentionally left to future presentation
  code.
- Smoothing does not reset after a missing interval. Research code must use the
  session audit to reject unsuitable datasets before treating results as
  continuous-market indicators.

