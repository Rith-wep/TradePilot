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

## Deterministic strategy engine

The pure `tradepilot.strategies` package detects research candidates from
validated completed candles and aligned indicators. It does not simulate
orders, entries, fills, position size, profit, or strategy performance.

Every immutable setup records strategy/version, instrument, timeframe, the
detection candle's opening timestamp, the completed-candle observability time,
direction, rule evidence, indicators, invalidation descriptions, a
non-executable `structural_invalidation_reference`, and a deterministic
configuration fingerprint. For H1 candle open `t`, the candidate is observable
only at `t + 1 hour`, never at `t`.

### Price Range Breakout v1

Default lookback is 20 and default price basis is midpoint:

```text
range_high = maximum high over [t-N, ..., t-1]
range_low  = minimum low over [t-N, ..., t-1]

LONG:  close[t] > range_high
SHORT: close[t] < range_low
```

The current candle is excluded and equality never triggers. An optional
minimum distance can be configured as a Decimal multiple of ATR. The broken
range boundary is the structural invalidation reference.

### EMA/RSI Trend Pullback v1

Defaults are EMA 200, RSI 14, ATR 14, recovery level 50, and midpoint prices:

```text
LONG:
  EMA[t] > EMA[t-1]
  close[t-1] <= EMA[t-1]
  close[t] > EMA[t]
  RSI[t] > 50
  RSI[t] > RSI[t-1]

SHORT:
  EMA[t] < EMA[t-1]
  close[t-1] >= EMA[t-1]
  close[t] < EMA[t]
  RSI[t] < 50
  RSI[t] < RSI[t-1]
```

The immediate previous-candle condition requires a fresh recovery crossover,
preventing repeated candidates when price simply remains on the same side of
the EMA. Structural references are `low[t-1] - ATR[t]` for LONG and
`high[t-1] + ATR[t]` for SHORT. They are research references, not stop orders.

Expected configured session closures are allowed; unexpected missing H1
intervals reject detection by default. Indicator timestamps must align exactly,
warm-up values suppress candidates, duplicates are removed by stable identity,
and prefix tests enforce causality.

### Run a strategy

```powershell
tradepilot-strategy data/mock/EURUSD/H1 breakout --lookback 20

tradepilot-strategy data/mock/EURUSD/H1 pullback `
  --ema-period 200 --rsi-period 14 --atr-period 14
```

Output contains candidate facts and rule evidence only—never simulated profit
or performance metrics.

## Reproducible candidate-signal reports

The provider-neutral `tradepilot.reporting` package converts a verified dataset
and immutable setup records into a content-addressed JSON research report. It
does not calculate outcomes or performance metrics.

Deterministic report content includes dataset ID/checksum, strategy and
configuration identity, indicator parameters, price basis, session calendar,
gap policy, research engine version, implementation revision, and exact signal
evidence. The run creation timestamp is stored separately and does not affect
report identity.

Canonical JSON uses UTF-8, sorted keys, compact separators, UTC `Z` timestamps,
and exact Decimal strings. The report ID is SHA-256 over canonical deterministic
content. Implementation revision is included in identity: this prevents reports
from different known code revisions appearing equivalent, at the cost of a new
ID even when a code change does not affect results. The CLI prefers
`TRADEPILOT_IMPLEMENTATION_REVISION`, then a Git commit SHA, and falls back to
`unknown` without requiring Git.

H1 report validation requires:

- detection timestamp exactly matches a candle in the verified dataset;
- `observable_at = detection candle open + 1 hour`;
- signal strategy, configuration, instrument, timeframe, and dataset
  provenance match the run; and
- duplicate candidate identities are absent.

Valid zero-candidate reports are supported.

### Generate and verify

```powershell
tradepilot-research-report generate `
  data/mock/EURUSD/H1 breakout `
  --output reports --lookback 20

tradepilot-research-report generate `
  data/mock/EURUSD/H1 pullback `
  --output reports `
  --ema-period 200 --rsi-period 14 --atr-period 14

tradepilot-research-report verify reports/{report-id}
```

Storage layout:

```text
reports/{report-id}/report.json
reports/{report-id}/runs/{run-metadata-id}.json
```

Complete report directories are staged under the same report root before an
atomic directory rename publishes them. Concurrent identical writers verify and
reuse the winner. Existing immutable reports are never overwritten; incomplete
or corrupt destinations are rejected. This assumes a local filesystem with
atomic same-filesystem rename and hard-link support. Network filesystems or
unusual filesystems may provide weaker guarantees; cross-filesystem staging is
intentionally not used.

## Backtesting domain foundation

The provider-neutral `tradepilot.backtesting` package defines immutable
contracts for the future event-driven simulator. It does not run simulations,
match orders, calculate P&L, or produce performance metrics.

`BacktestConfig` binds a verified dataset and immutable candidate report to
versioned execution, cost, financing, risk, instrument, currency, session, and
implementation assumptions. Its canonical SHA-256 identity excludes the
separate run creation timestamp.

At one H1 boundary, chronological information availability is:

```text
completed previous candle -> signal observable -> next opening quote
```

Opening events expose bid/ask opens only. Full bid/ask OHLC is unavailable until
the candle completes, preventing future high, low, or close values from
influencing entry decisions.

Only market-at-next-eligible-open requests are modeled. Every request has an
explicit expiry. Expected session closures may be skipped while it remains
valid; strict unexpected gaps reject execution. A position can be created only
from a validated pending-order entry fill.

LONG entry/exit uses ask/bid; SHORT entry/exit uses bid/ask. Additional spread
stress widens the observed quote symmetrically and adverse slippage is separate,
so quoted spread is not double-counted. Stops and targets must be explicit;
structural invalidation references are never converted automatically.

Cross-currency valuation requires timestamped, sourced observations available
no later than each financial event. Conversion and other monetary calculations
remain future work. See `docs/phases/phase-3-step-1.md` for lifecycle,
stop/target ordering, policies, and limitations.

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
- Strategy candidates are unvalidated research hypotheses, not evidence of
  profitability or trading recommendations.
- Only H1 completed-candle observability is currently mapped.
- Structural invalidation references are not executable stops and do not model
  spreads, slippage, gaps, or fills.
- Report verification proves internal content integrity but does not
  automatically re-download or independently authenticate the original market
  data provider.
- The `unknown` revision fallback cannot distinguish different uncommitted or
  unavailable code revisions.
- Backtesting currently provides domain contracts only; there is no event loop,
  order matching, P&L, trade log, or performance reporting.

