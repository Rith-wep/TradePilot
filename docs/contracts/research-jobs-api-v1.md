# Research jobs API v1

All routes use the `tradepilot-api/v1` envelope and require a valid OIDC bearer
token. Jobs are lifecycle records, not research results or live signals.

## Submission

`POST /api/v1/research-jobs` requires `researcher` or `admin` and returns HTTP
202. The body has exactly these fields:

```json
{
  "contractVersion": "tradepilot-research-job-request/v1",
  "idempotencyKey": "client_request_001",
  "datasetId": "64-lowercase-hex-characters",
  "instrument": "EURUSD",
  "timeframe": "H1",
  "strategy": {"name": "price_range_breakout", "version": "v1"}
}
```

Supported instruments are `EURUSD` and `GBPUSD`; timeframe is `H1`; strategy
is `price_range_breakout/v1` or `ema_rsi_trend_pullback/v1`. The dataset must
already be verified in the catalog and its provenance must match. Unknown
fields, arbitrary paths, commands, and parameters are rejected.

## Reads

- `GET /api/v1/research-jobs/` returns the caller's jobs, bounded to 100.
  Administrators see all jobs.
- `GET /api/v1/research-jobs/:jobId` returns a job only to its owner or an
  administrator. A non-owner receives 404 to avoid disclosing existence.

States are `QUEUED`, `RUNNING`, `SUCCEEDED`, `FAILED`, and `CANCELLED`. No Step
10 endpoint returns or fabricates a research result. After controlled execution,
a `SUCCEEDED` job includes `resultReportId`; the database requires that ID to
already exist in the verified candidate-report catalog.

