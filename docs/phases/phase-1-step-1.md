# Phase 1, Step 1: Python Workspace and Data Validation

**Status:** Complete  
**Scope:** Research workspace, canonical candle contract, synthetic fixture,
and deterministic quality validation.

## Goal

Create a small Python research package that can represent and validate H1 forex
candles without requiring vendor credentials. This step intentionally excluded
indicators, strategies, backtesting, APIs, and user interfaces.

## What was implemented

- A Python 3.12+ package under `research/`.
- Immutable typed models for FX instrument metadata and bid/ask candles.
- Exact decimal price handling with `Decimal` instead of binary floating point.
- UTC-aware H1 candle-open timestamp conventions.
- A strict CSV loader with readable row-level errors.
- Candle validation for:
  - UTC and hour-aligned timestamps;
  - chronological ordering and duplicate timestamps;
  - positive and internally consistent bid/ask OHLC values;
  - bid prices not exceeding corresponding ask prices;
  - H1 timeframe and required provenance fields; and
  - missing intervals, reported as warnings without creating fake candles.
- A clearly labeled five-row synthetic EUR/USD fixture.
- A CLI that prints a deterministic JSON quality report.
- Automated tests for valid and invalid inputs.

## Technical decisions

- Candle timestamps represent the beginning of each H1 interval.
- All timestamps must be timezone-aware UTC.
- Missing bars are never filled automatically because a gap may represent a
  weekend, holiday, or data-source failure.
- The synthetic fixture is test data only and must not be presented as market
  history.
- Standard-library `unittest` keeps the initial test setup dependency-light.

## Main files

```text
research/pyproject.toml
research/README.md
research/fixtures/synthetic_eurusd_h1.csv
research/src/tradepilot/data/models.py
research/src/tradepilot/data/csv_loader.py
research/src/tradepilot/data/validation.py
research/src/tradepilot/data/cli.py
research/tests/test_models.py
research/tests/test_loader.py
research/tests/test_validation.py
research/tests/test_cli.py
```

## Commands

From `research/`:

```powershell
$env:PYTHONPATH = "src"
python -m tradepilot fixtures/synthetic_eurusd_h1.csv
python -m unittest discover -s tests -v
```

## Verification result

The completion run used Python 3.12.6.

```text
Fixture candles: 5
Validation errors: 0
Validation warnings: 0
Validation result: valid

Ran 10 tests
OK
```

## Limitations at completion

- Only a synthetic EUR/USD fixture was included.
- There was no provider abstraction or historical ingestion.
- There was no Parquet persistence.
- Gap warnings did not classify weekends or holidays.

## Next step

Phase 1, Step 2: add a provider-neutral historical ingestion pipeline and local
Parquet persistence. This next step was subsequently approved and completed.

