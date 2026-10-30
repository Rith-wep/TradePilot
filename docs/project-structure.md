# Project structure

Related guides: [developer onboarding](onboarding.md) and [package dependency
map](package-dependencies.md).

## Repository map

```text
TradePilot/
├── README.md                       # product scope and roadmap
├── docs/
│   ├── README.md                   # completed milestone index
│   ├── architecture.md             # boundaries and identity policy
│   ├── project-structure.md        # this file
│   ├── data-flow.md                # chronological artifact flow
│   ├── development.md              # setup, tests and CLI reference
│   └── phases/                     # milestone implementation reports
└── research/
    ├── pyproject.toml              # package, dependencies and entry points
    ├── README.md                   # research-user documentation
    ├── fixtures/                   # committed synthetic fixtures/templates
    ├── src/tradepilot/             # installable package
    └── tests/                      # unit and integration tests
```

Generated or local-only directories are intentionally not source code:

```text
research/.venv/                     # local Python environment
research/data/                      # immutable local datasets
research/reports/                   # generated candidate/readiness reports
research/raw/                       # recommended local provider CSV location
```

Provider market exports, API credentials, generated Parquet files and research
reports must not be committed. The existing root-level Dukascopy export naming
pattern is ignored for compatibility; new local exports should use
`research/raw/` after that ignored directory is introduced in an approved
maintenance change.

## Package map

```text
tradepilot/
├── core/                          # canonical JSON and SHA-256 helpers
├── data/
│   ├── providers/                  # provider protocol, mock, OANDA, Dukascopy
│   ├── models.py                   # Instrument and Candle
│   ├── normalization.py            # untrusted provider record -> Candle
│   ├── validation.py               # candle quality rules
│   ├── sessions.py                 # configurable market-session calendars
│   ├── ingestion.py                # batching, retries and normalization
│   ├── storage.py                  # immutable Parquet snapshot facade
│   ├── integrity.py                # manifest and checksum verification
│   ├── source_artifacts.py         # batch source provenance
│   ├── readiness*.py               # real-data readiness evidence
│   └── *_cli.py                    # data command adapters
├── indicators/                     # typed indicator series and calculations
├── strategies/                     # candidate rules and evidence models
├── reporting/                      # immutable candidate research reports
├── backtesting/                    # execution domain and simulator
├── accounting/                     # financial reconstruction and metrics
├── validation/                     # research validation and governance
└── workflows/
    ├── research_run.py             # shared candidate research construction
    └── real_data_readiness.py      # real-data verification workflow
```

`tradepilot.data.validation` means candle-quality validation.
`tradepilot.validation` means research partitioning and robustness validation.
This distinction is retained to avoid unnecessary module churn.

## Test organization

Tests currently use a flat discovery layout. Files are named for the behavior
under test, while reusable deterministic builders use `*_helpers.py`. The full
suite is the authoritative regression gate. Identity compatibility has an
additional explicit gate in `test_identity_golden.py`.

Do not reorganize tests and production modules in the same change. Separating
those operations keeps history reviewable and makes regressions easier to
localize.
