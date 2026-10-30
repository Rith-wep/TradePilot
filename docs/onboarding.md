# Developer onboarding

## Setup and first test run

TradePilot's implemented application is the Python workspace under
`research/`. Use Python 3.12 or newer.

```powershell
cd research
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e .
python -m unittest discover -s tests -v
```

The editable install supplies Apache Arrow, the Windows timezone database, and
all 11 `tradepilot-*` commands. If dependencies are already cached and network
access is intentionally unavailable, the build backend must already be
installed in the environment; do not bypass dependency installation and assume
the resulting environment is complete.

For a source checkout that already has its runtime dependencies, tests can also
run without installation:

```powershell
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -v
```

Use the virtual environment's Python explicitly when shell activation is
uncertain:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## Where to start

| Need | Start here |
| --- | --- |
| Candle contracts and quality | `src/tradepilot/data/models.py`, `data/validation.py` |
| Provider ingestion | `data/providers/`, `data/ingestion.py` |
| Immutable datasets | `data/storage.py`, `data/integrity.py` |
| EMA, RSI, ATR | `indicators/core.py` |
| Breakout and pullback rules | `strategies/breakout.py`, `strategies/pullback.py` |
| Shared candidate orchestration | `workflows/research_run.py` |
| Candidate report identity/storage | `reporting/models.py`, `reporting/storage.py` |
| Execution simulation | `backtesting/simulator.py` |
| Ledger and metrics | `accounting/` |
| Partition and validation governance | `validation/` |

Domain formulas belong in their domain package. Cross-package application use
cases belong in `workflows`. Argument parsing and terminal output belong in CLI
adapter modules.

## First reproducible workflow

The committed fixture is synthetic. From `research/`:

```powershell
tradepilot-validate fixtures/synthetic_eurusd_h1.csv
tradepilot-ingest-mock --input fixtures/synthetic_eurusd_h1.csv --output data
tradepilot-audit data/mock/EURUSD/H1
tradepilot-indicators data/mock/EURUSD/H1 --price-basis mid
tradepilot-strategy data/mock/EURUSD/H1 breakout --lookback 20
tradepilot-research-report generate data/mock/EURUSD/H1 breakout --output reports
```

The report command prints the content-addressed report ID. Verify the resulting
artifact independently:

```powershell
tradepilot-research-report verify reports/{report-id}
```

A valid report with zero candidates is still a reproducible result.

## Trace one candle into a candidate report

1. `data.integrity.verify_dataset` verifies the manifest, Parquet checksum and
   canonical dataset checksum, then returns canonical `Candle` records.
2. `workflows.research_run.evaluate_candidate_research` calculates only the
   indicators required by the selected strategy from completed candle prefixes.
3. The strategy records a `SetupRecord` only after its rule conditions pass.
   Its `detection_candle_open` identifies the source candle; for H1,
   `observable_at` is exactly one hour later.
4. `workflows.research_run.build_candidate_research_run` binds the setup to the
   dataset ID/checksum, strategy/version, configuration fingerprint, indicator
   parameters, price basis and session calendar.
5. `reporting.storage.ResearchReportStore` serializes canonical JSON and uses
   its SHA-256 content hash as the immutable report ID.

To inspect a particular timestamp, find it in the audit/indicator/strategy JSON
outputs, then locate the same `detection_candle_open` in the saved candidate
report. Never infer availability from the candle opening time: the observable
timestamp is the decision boundary.

## Change verification

```powershell
python -m unittest discover -s tests -p test_identity_golden.py -v
python -m unittest discover -s tests -p test_dependency_boundaries.py -v
python -m unittest discover -s tests -v
git diff --check
```

Do not update golden identity values to accommodate an unapproved change.

