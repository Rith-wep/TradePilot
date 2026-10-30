# Package dependency map

## Allowed direction

`core` is dependency-free infrastructure. Domain packages may depend only on
the packages to their left or on the specific lower-level contracts shown
below. `workflows` and CLI adapters are composition layers and are never domain
dependencies.

```text
core
  +-- data
  |     +-- indicators
  |           +-- strategies
  |                 +-- reporting
  |                       +-- backtesting
  |                             +-- accounting
  |
  +-------------------------------- validation

data + indicators + strategies + reporting
                    -> workflows/research_run

data + research_run + reporting
                    -> workflows/real_data_readiness

domain packages -> X workflows
domain packages -> X CLI adapters
data            -> X indicators/strategies/reporting/validation
```

The horizontal diagram is a review aid, not permission for every package to
import every package to its left. Actual responsibilities are:

| Package | May depend on |
| --- | --- |
| `core` | Python standard library |
| `data` | `core`; provider/runtime libraries such as PyArrow |
| `indicators` | canonical candle models from `data` |
| `strategies` | `data`, `indicators` |
| `reporting` | `core`, `data`, strategy records |
| `backtesting` | `core`, verified data/report contracts, strategy records |
| `accounting` | `core`, immutable backtesting results |
| `validation` | lower research layers required to evaluate frozen research |
| `workflows` | any domain package needed by the application use case |
| CLI modules | workflows or domain APIs; they own presentation and exit codes |

## Compatibility shims

Compatibility shims preserve an old public import path; they must contain no
new domain behavior.

| Shim | Canonical implementation | Reason |
| --- | --- | --- |
| `tradepilot.reporting.canonical` | `tradepilot.core.canonical` | Preserve canonical utility imports |
| `tradepilot.data.readiness_pipeline` | `tradepilot.workflows.real_data_readiness` | Preserve pre-Step-3 readiness imports |

`tests/test_dependency_boundaries.py` explicitly permits only the readiness
shim as a data-to-workflow exception. CLI files (`cli.py` and `*_cli.py`) are
interface adapters and may import workflows. New exceptions require written
architecture documentation and a focused compatibility test.

## Enforcement

- `tests/test_dependency_boundaries.py` parses imports and rejects reverse
  workflow/CLI dependencies and higher-level imports from the data domain.
- `tests/test_cli_entry_points.py` verifies the exact command inventory and
  ensures every configured target is importable and callable.
- `tests/test_identity_golden.py` prevents architectural cleanup from changing
  canonical bytes or content identities.

