# Data and research flow

## Historical data

```text
Provider response or paired CSV files
              |
              v
ProviderCandle records (untrusted)
              |
              v
UTC/Decimal normalization
              |
              v
Candle validation + session-gap classification
              |
              v
Immutable Parquet snapshot
  - dataset ID
  - canonical checksum
  - Parquet checksum
  - provider/retrieval provenance
  - optional source-artifact manifest
              |
              v
Independent integrity verification
```

Requests and stored ranges are half-open: `[start, end)`. CSV BID and ASK rows
must align exactly. Pagination, retries and rate limits belong to provider and
ingestion layers; downstream research is provider-neutral.

## Candidate research

```text
Verified immutable candles
        |
        +--> EMA / RSI / ATR
        |
        v
Versioned deterministic strategy
        |
        v
Immutable candidate setups
  - detection candle opening time
  - completed-candle observable time
  - direction and rule evidence
  - structural invalidation reference
        |
        v
Content-addressed candidate report
```

Indicators and strategies consume only completed historical prefixes. Candidate
generation must remain prefix invariant and cannot access future candles.

## Simulation and accounting

```text
Verified dataset + candidate report + execution configuration
                             |
                             v
Event-driven simulator
  candle close -> signal observable -> next eligible opening quote
                             |
                             v
Immutable audit log, orders, fills and positions
                             |
                             v
Accounting reconstruction
  conversions -> ledger -> equity -> metrics
```

LONG entries use ASK and exits use BID. SHORT entries use BID and exits use ASK.
Opening protection checks precede intrabar checks. Ambiguous intrabar stop and
target ordering uses the documented conservative policy; it does not claim to
reconstruct the true tick sequence.

## Chronological validation

```text
Exact immutable dataset identity
              |
              v
Chronological 60 / 20 / 20 partition plan
  training | validation | locked test
              |
              +--> expanding walk-forward validation
              +--> execution-cost stress scenarios
              +--> deterministic block bootstrap when eligible
              |
              v
Sealed locked-test governance record
```

Historical indicator warm-up may use candles before a partition boundary, but
signals and execution must remain inside the selected partition. Sealing a test
partition does not authorize its evaluation.

## Failure policy

The pipeline fails closed on malformed provider data, invalid timestamps,
conflicting duplicates, unexplained strict-mode gaps, checksum failure,
corrupted manifests, provenance mismatch, unapproved historical revisions, or
missing required credentials. Synthetic data is never substituted for missing
real market data.
