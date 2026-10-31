# Research catalog API v1

The catalog API is a read-only view of metadata already registered through the
trusted Python verification boundary. All responses use the existing
`tradepilot-api/v1` success or error envelope.

## Pagination

All collection endpoints accept:

- `limit`: integer from 1 through 100; default 25.
- `cursor`: opaque cursor returned by the same endpoint.

Unknown, repeated, malformed, oversized, or cross-endpoint cursors are rejected
with HTTP 400 and `VALIDATION_ERROR`. Results use ascending immutable keys:
instrument symbol, dataset ID, or report ID. The response data contains
`items`, `nextCursor`, and `historicalOnly: true`.

## GET /api/v1/instruments

Also available with a trailing slash. Each item contains:

- `symbol`, `baseCurrency`, and `quoteCurrency`
- exact string `pipSize` and integer `pricePrecision`
- UTC `verifiedAt`
- `classification: "FOREX_INSTRUMENT"`

Only instruments referenced by at least one verified dataset are returned.

## GET /api/v1/datasets

Each item contains:

- immutable `datasetId` and `canonicalChecksum`
- `instrument`, `provider`, and `timeframe`
- UTC `firstCandleOpen`, `lastCandleOpen`, and `verifiedAt`
- string `rowCount` and `schemaVersion`
- `dataClassification: "HISTORICAL"`
- `sourceClassification: "SYNTHETIC"` or `"MARKET_DATA"`

## GET /api/v1/candidate-reports

Each item contains:

- immutable `reportId` and referenced `datasetId`
- `strategyName`, `strategyVersion`, and `configurationFingerprint`
- `schemaVersion`, integer `signalCount`, and UTC `verifiedAt`
- `classification: "HISTORICAL_RESEARCH_CANDIDATES"`
- `sourceClassification: "SYNTHETIC"` or `"MARKET_DATA"`
- `liveSignal: false`

## Security boundary

The API reads PostgreSQL only. It does not open artifacts, run Python, execute
research, register catalog rows, or expose a verification endpoint. Storage
keys, paths, Parquet content, verifier details, and database errors are never
returned.

There is no authentication yet. The server validates a loopback-only bind host,
and catalog routes fail closed in production. These endpoints must not be made
reachable through a proxy, container port, tunnel, or nonlocal bind until an
approved authorization layer exists.
