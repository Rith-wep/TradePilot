# Phase 4, Step 1: OANDA Historical Forex Data Integration

**Status:** Complete  
**Scope:** OANDA v20 EUR/USD and GBP/USD H1 bid/ask ingestion. No strategy,
simulation, accounting, or validation-formula changes.

## Architecture

`OandaMarketDataProvider` implements the existing provider-neutral
`MarketDataProvider` interface. Provider-specific HTTP, authentication, symbol
mapping, pagination, and response parsing remain isolated in
`data/providers/oanda.py`.

```text
OANDA v20 HTTPS
  -> OANDA adapter (untrusted ProviderCandle)
  -> shared Decimal/UTC normalization
  -> shared validation and session-aware gap audit
  -> immutable content-addressed Parquet snapshot
  -> manifest, canonical checksum, file checksum, retrieval provenance
  -> independent integrity verification
```

Only `EUR_USD`/`EURUSD`, `GBP_USD`/`GBPUSD`, H1, and `price=BA` are supported.
Every response must match its requested instrument, H1 granularity, and
half-open page interval. Incomplete candles and malformed responses fail closed.
Missing candles are never created and midpoint prices are never converted into
bid/ask values.

## Configuration and credentials

Credentials are read only from the process environment:

```powershell
$env:OANDA_API_TOKEN = "..."
$env:OANDA_ACCOUNT_ID = "..."
```

They are not stored in source, output JSON, manifests, retrieval records, or
error messages. Supported environments are `practice` and `live`; practice is
the default.

```powershell
cd research
$env:PYTHONPATH = "src"
tradepilot-ingest-oanda EURUSD `
  --start 2024-01-01T00:00:00Z `
  --end 2024-02-01T00:00:00Z `
  --environment practice `
  --output data
```

The command supports configurable request rate, timeout, retry count, and batch
duration. The adapter uses persistent-library defaults where possible, limits
requests locally, converts HTTP 429 into a retryable error with `Retry-After`,
and treats timeouts/5xx responses as transient. Authentication and schema errors
are permanent.

## Pagination and timestamps

OANDA documents a maximum of 5,000 candles per request. The adapter uses
deterministic, contiguous time pages of at most 5,000 H1 boundaries. Cursors are
UTC timestamps and must remain strictly inside the original request. Every
returned candle is verified against `[page_start,page_end)` before shared
normalization verifies the complete ingestion range.

OANDA timestamps are stored as UTC candle-opening timestamps. Only candles with
`complete=true` are accepted.

## Quality and provenance

Existing checks reject invalid timestamps, OHLC relationships, bid above ask,
conflicting duplicates, missing provenance, and corrupt snapshots. Identical
duplicates are counted and deterministically deduplicated. Gaps remain present
and are classified by the configured market-session calendar.

A spread over the configurable validation threshold (20 pips by default) adds
an `unusual_spread` warning while retaining an otherwise valid candle. Negative
spreads remain errors. The warning is an audit flag, not an automatic outlier
filter.

Retrieval records preserve adapter version, OANDA environment, provider symbol,
granularity, price component, request ID, requested range, and retrieval time.
Credentials are excluded. Canonical content determines dataset identity;
retrieval metadata does not.

## Tests

Default tests inject synthetic OANDA-shaped HTTP responses and never access the
network. They cover EUR/USD and GBP/USD mapping, bid/ask parsing, UTC/page
boundaries, pagination, incomplete and malformed data, unsupported requests,
429 handling, credential redaction, throttling, missing credentials, and spread
warnings.

The optional practice smoke test is disabled unless explicitly enabled:

```powershell
$env:TRADEPILOT_RUN_OANDA_SMOKE = "1"
python -m unittest tests.test_oanda_practice_smoke
```

It requires valid practice credentials and is not part of deterministic CI.

## Licensing and limitations

- OANDA data is broker-specific, not a consolidated interbank feed.
- H1 bid/ask candles are aggregates, not tick history or guaranteed executable
  quotes.
- Historical data may be revised; revisions require the existing explicit
  snapshot revision policy.
- Account/API availability depends on region and OANDA account eligibility.
- OANDA licensed material is intended for internal use and generally cannot be
  redistributed. Generated datasets remain git-ignored and must not be shared
  without appropriate permission.
- Session and holiday classification is only as accurate as the configured
  broker calendar.
- The smoke test cannot verify access without user-supplied credentials and
  network access.

References: [OANDA v20 candle API](https://developer.oanda.com/rest-live-v20/pricing-ep/),
[development limits](https://developer.oanda.com/rest-live-v20/development-guide/),
[API license](https://legal.oanda.com/oc/api_license_agreement_oc/en).

## Next step

Stop here and wait for approval before Phase 4, Step 2.
