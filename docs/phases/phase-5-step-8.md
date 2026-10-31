# Phase 5, Step 8: Read-only Candidate Evidence APIs

Status: implemented, pending review and commit.

## Scope

This step adds ID-based catalog details and bounded candidate-evidence APIs. A
Python contract verifies immutable report integrity before projecting supported
evidence. No report content, research formula, or identity changed.

## Routes

- `GET /api/v1/instruments/:symbol`
- `GET /api/v1/datasets/:datasetId`
- `GET /api/v1/candidate-reports/:reportId`
- `GET /api/v1/candidate-reports/:reportId/candidates`
- `GET /api/v1/evidence/:candidateEvidenceId`

Trailing slash forms are supported. Candidate pages contain at most 100 records
and use deterministic report-bound cursors.

## Trust and safety

Node requires the report in PostgreSQL, then invokes the fixed Python evidence
module through the shared controlled subprocess runner. Python accepts only an
approved report root, verifies report integrity, and returns a schema-validated
projection. Evidence is historical, never a recommendation or live signal.

## Verification

```powershell
cd server
docker compose up -d postgres
$env:TEST_DATABASE_URL = "postgresql://tradepilot:tradepilot@localhost:54329/tradepilot"
npm test
npm run typecheck
npm run build

cd ..\research
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## Limitations

- Authentication and authorization are not implemented.
- Projection starts a Python subprocess per request.
- Evidence IDs are projections, not new canonical report content.
- No frontend, worker, recommendation, or live-signal behavior exists.
