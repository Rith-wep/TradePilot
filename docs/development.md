# Development guide

New contributors should begin with the concise [developer onboarding
guide](onboarding.md), then use this page as the command and review reference.

## Requirements and setup

- Python 3.12 or newer
- PowerShell examples below; equivalent shell commands are acceptable

```powershell
cd research
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e .
```

The runtime package installs `pyarrow` and Windows `tzdata`. The authoritative
suite uses Python `unittest`; pytest is optional and is not a runtime dependency.

```powershell
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -v
```

Run only the identity compatibility gate:

```powershell
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -p test_identity_golden.py -v
```

## CLI command reference

| Command | Purpose |
| --- | --- |
| `tradepilot-validate` | Validate the committed canonical CSV fixture format |
| `tradepilot-ingest-mock` | Ingest labeled synthetic candles through the provider-neutral pipeline |
| `tradepilot-ingest-oanda` | Credential-gated bounded OANDA H1 BID/ASK ingestion |
| `tradepilot-oanda-readiness` | Connectivity, ingestion, integrity and research-readiness evidence |
| `tradepilot-import-dukascopy` | Import one paired Dukascopy BID/ASK CSV range |
| `tradepilot-import-dukascopy-batch` | Strict manifest-driven monthly batch import and partition sealing |
| `tradepilot-audit` | Verify a stored dataset and report quality/session gaps |
| `tradepilot-indicators` | Calculate EMA, RSI and ATR from a verified snapshot |
| `tradepilot-strategy` | Detect versioned candidate setups without performance claims |
| `tradepilot-research-report` | Generate or verify an immutable candidate report |
| `tradepilot-backtest` | Run the deterministic simulator and emit an execution trace |
| `tradepilot-verify-artifact` | Verify one immutable dataset or candidate report through the machine contract |

Use `COMMAND --help` for command-specific arguments. OANDA commands read
credentials from `OANDA_API_TOKEN` and `OANDA_ACCOUNT_ID`; secrets must not be
placed in source files, manifests or reports.

The 12-command inventory is defined in `research/pyproject.toml` and guarded by
`tests/test_cli_entry_points.py`. After changing entry points, rerun the editable
install so the virtual environment's generated command wrappers are refreshed.

## Local directories

- `fixtures/`: committed synthetic data and non-runnable templates only.
- `raw/`: recommended ignored location for licensed local CSV exports.
- `data/`: generated immutable Parquet snapshots and manifests.
- `reports/`: generated research/readiness report artifacts.
- `.venv/`: local environment.

Never commit real provider exports, credentials, generated datasets, or
proprietary reports. Do not edit an immutable snapshot in place.

## Review checklist

Before submitting a change:

1. Confirm the request authorizes the affected milestone and behavior.
2. Keep strategy, execution and accounting formula changes separate from
   structural refactors.
3. Run focused tests for the touched package.
4. Run `test_identity_golden.py` for any serialization, model, storage or
   provenance change.
5. Run the complete suite.
6. Run `git diff --check` and review every changed file.
7. Report actual commands and results; do not claim unexecuted verification.

Golden identity constants may change only with an approved versioned migration.
Refactoring alone is not a reason to update them.

## Current tooling limitations

There is no committed CI workflow, formatter, linter, static type checker,
coverage threshold or development dependency group yet. The current test stack
needs no additional development dependency: `unittest` and the new TOML/entry
point check use the Python 3.12 standard library. The minimal next tooling step
is a CI job that performs editable installation and runs the documented gates.
Formatter, linter, type checker and coverage dependencies should be proposed
with their configurations and adoption policy, not added unused.

The current architectural issues and backend integration gates are classified
in the [backend readiness review](backend-readiness.md).
