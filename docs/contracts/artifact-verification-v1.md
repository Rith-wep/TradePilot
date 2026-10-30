# Artifact verification contract v1

## Purpose

`tradepilot-artifact-verification/v1` is the trusted machine boundary for
verifying an already-existing immutable dataset or candidate report. It does
not ingest data, run indicators or strategies, generate reports, write to
PostgreSQL, or catalog artifacts.

The implementation is:

```text
tradepilot.contracts.artifact_verification
tradepilot.contracts.cli
```

JSON Schemas live in `research/contracts/`. Deterministic request fixtures live
in `research/fixtures/contracts/`.

## Invocation

The future Node worker must launch a fixed command without a shell and pass
approved roots as process configuration:

```powershell
tradepilot-verify-artifact `
  --dataset-root E:\approved\datasets `
  --report-root E:\approved\reports
```

One request is read from stdin. Exactly one compact JSON response plus a newline
is written to stdout. Diagnostics, limited to trusted configuration failures,
go to stderr. The request limit is 65,536 bytes.

The roots may instead be set through `TRADEPILOT_DATA_ROOT` and
`TRADEPILOT_REPORT_ROOT`. They are trusted operator/worker configuration and
must never come from an HTTP client.

## Dataset request

```json
{
  "contract_version": "tradepilot-artifact-verification/v1",
  "request_id": "node-request-01",
  "operation": "verify_artifact",
  "artifact": {
    "kind": "dataset",
    "artifact_id": "64 lowercase hexadecimal characters",
    "provider": "dukascopy-csv",
    "instrument": "EURUSD",
    "timeframe": "H1"
  }
}
```

The adapter constructs only this location:

```text
DATASET_ROOT/provider/instrument/timeframe/snapshots/artifact_id
```

Each locator component has a closed character grammar. The resolved path must
remain beneath the approved root, including after symlink resolution.

## Candidate-report request

```json
{
  "contract_version": "tradepilot-artifact-verification/v1",
  "request_id": "node-request-02",
  "operation": "verify_artifact",
  "artifact": {
    "kind": "candidate_report",
    "artifact_id": "64 lowercase hexadecimal characters"
  }
}
```

Only `REPORT_ROOT/artifact_id` can be addressed. Requests cannot contain a
filesystem path.

## Verified response

```json
{
  "contract_version": "tradepilot-artifact-verification/v1",
  "request_id": "node-request-01",
  "status": "VERIFIED",
  "artifact": {
    "kind": "dataset",
    "artifact_id": "..."
  },
  "verification": {
    "dataset_id": "...",
    "dataset_checksum": "...",
    "parquet_checksum": "...",
    "provider": "dukascopy-csv",
    "instrument": "EURUSD",
    "timeframe": "H1",
    "pip_size": "0.0001",
    "first_timestamp": "2025-01-01T00:00:00Z"
  }
}
```

The actual response includes the verified metadata appropriate to the artifact.
Decimal values remain JSON strings. Timestamps remain UTC `Z` strings. IDs and
checksums are copied from independently verified canonical content. No local
filesystem path is returned.

## Error response

```json
{
  "contract_version": "tradepilot-artifact-verification/v1",
  "request_id": "node-request-01",
  "status": "ERROR",
  "error": {
    "code": "ARTIFACT_VERIFICATION_FAILED",
    "message": "dataset integrity verification failed",
    "retryable": false,
    "details": {
      "issues": [
        {"code": "parquet_checksum_mismatch", "severity": "error"}
      ]
    }
  }
}
```

Stable error classes include:

- `INVALID_JSON`, `INVALID_REQUEST`, and `REQUEST_TOO_LARGE`;
- `UNSUPPORTED_CONTRACT`, `UNSUPPORTED_OPERATION`, and
  `UNSUPPORTED_ARTIFACT_KIND`;
- `ARTIFACT_NOT_FOUND`, `ARTIFACT_ID_MISMATCH`,
  `ARTIFACT_PATH_UNSAFE`, and `ARTIFACT_VERIFICATION_FAILED`;
- `CONFIGURATION_ERROR` for unavailable approved roots.

Exit code `0` means verified, `2` means request/contract rejection, `3` means
artifact verification failure, and `4` means trusted process configuration
failure.

## Security assumptions

- Node supplies fixed approved roots; the client supplies only the JSON request.
- Node invokes a fixed executable/module without a shell.
- The process runs with read-only artifact mounts in production.
- Unknown and duplicate JSON fields are rejected.
- IDs and dataset locator fields use strict allowlists.
- Missing, corrupted, mismatched, noncanonical, or unsupported artifacts fail
  closed.
- Existing Python verification functions remain authoritative.
- Error details expose issue codes and severity, not local paths or raw provider
  payloads.
- Successful verification does not authorize PostgreSQL insertion by itself;
  Node must bind the response to the originating request and approved policy.

## Identity compatibility

The adapter does not rewrite artifacts or calculate alternative identities. It
calls `verify_dataset` or `verify_report`, then returns verified metadata. It
does not modify research formulas, canonical JSON, Decimal serialization,
timestamps, provenance, or content-addressed IDs.
