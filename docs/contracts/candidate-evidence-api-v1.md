# Candidate evidence API v1

Candidate evidence is a bounded read-only projection of an integrity-verified
immutable candidate report. It is historical research context, not a trading
recommendation or live signal.

## Endpoints

```text
GET /api/v1/candidate-reports/:reportId/candidates
GET /api/v1/evidence/:candidateEvidenceId
```

Both accept trailing slashes. The collection supports `limit` from 1 through
100 and a report-bound opaque `cursor`.

## Candidate fields

When present in the source report, the projection includes timestamps,
direction, strategy configuration identity, indicator context, rule evidence,
structural invalidation research reference, and immutable provenance.

Every candidate is classified as `HISTORICAL_RESEARCH` with
`liveSignal: false`. Structural invalidation remains a non-executable research
reference. The projection makes no profitability claim and supplies no trading
recommendation.

## Identity and integrity

The evidence ID contains the immutable report ID, zero-padded signal ordinal,
and SHA-256 digest of the canonical signal. Detail lookup reverifies the report
and recomputes the evidence ID. Node validates both contract messages against
committed JSON schemas.

## Security

- No request contains a filesystem path.
- Node never returns or reads canonical `report.json` directly.
- Output, input, time, concurrency, pending work, and candidate count are bounded.
- Missing, corrupted, mismatched, malformed, or oversized evidence fails closed.
- Routes are loopback-only and disabled in production until authorization exists.
