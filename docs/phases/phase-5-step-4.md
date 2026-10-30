# Phase 5, Step 4: Trusted Python Artifact Verification Contract

**Status:** Complete
**Scope:** Read-only Python subprocess contract for existing immutable artifacts.
No HTTP, PostgreSQL insertion, research execution, worker, or formula changes.

## Result

A versioned stdin/stdout adapter now verifies datasets and candidate reports by
reusing the existing `verify_dataset` and `verify_report` implementations.
Requests contain immutable IDs and strict dataset locator identifiers, never
paths. Dataset and report roots are trusted process configuration.

The adapter rejects unknown/duplicate fields, invalid identifiers, requests
over 65,536 bytes, unsupported contract versions/operations/artifact kinds,
root escapes, missing artifacts, corrupt content, and identity mismatches.

Successful output preserves verified SHA-256 IDs/checksums, exact Decimal
strings, UTC timestamps, schema and provider provenance, strategy provenance,
and quality metadata. It never returns local filesystem paths.

## Main files

```text
research/src/tradepilot/contracts/artifact_verification.py
research/src/tradepilot/contracts/cli.py
research/contracts/artifact-verification-v1.request.schema.json
research/contracts/artifact-verification-v1.response.schema.json
research/fixtures/contracts/
research/tests/test_artifact_verification_contract.py
docs/contracts/artifact-verification-v1.md
```

## Command

```powershell
cd research
tradepilot-verify-artifact `
  --dataset-root path\to\approved\data `
  --report-root path\to\approved\reports `
  < request.json
```

Future Node integration must spawn this fixed command without a shell, write one
bounded request to stdin, enforce a timeout/output limit, validate the response
contract, and bind it to the original request before catalog insertion.

## Verification coverage

- Valid deterministic dataset verification.
- Valid candidate-report verification.
- Exact Decimal, UTC timestamp, checksum, identity, and provenance output.
- Missing datasets/reports.
- Corrupted Parquet and report JSON.
- Requested/content identity mismatch.
- Unsupported versions and artifact kinds.
- Unknown fields, invalid locator input, duplicate JSON, and oversized input.
- Single-line machine-readable CLI output with clean stderr for contract errors.

Actual verification results:

- Python full suite: 242 passed, 2 credential-gated OANDA tests skipped.
- Node suite against PostgreSQL 17: 11 passed, 0 skipped.
- Node strict typecheck and build: passed.
- `git diff --check`: passed.

## Limitations

- The contract verifies only existing dataset snapshots and candidate reports.
- Root selection is trusted process configuration; deployment permissions must
  make artifact mounts read-only.
- No Node subprocess runner, timeout enforcement, catalog insertion, discovery,
  HTTP endpoint, or authorization is implemented yet.
- The response schema intentionally allows artifact-specific verification
  metadata; compatibility changes still require a new contract version.

## Next step

Stop for approval before adding the controlled Node subprocess runner or any
automatic catalog insertion.
