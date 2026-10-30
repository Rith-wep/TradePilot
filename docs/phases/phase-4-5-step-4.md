# Phase 4.5, Step 4: Shared Research Workflow

**Status:** Complete  
**Checkpoint:** `92434b4 refactor(workflows): share research orchestration`

## Result

`tradepilot.workflows.research_run` now centralizes shared construction of
strategy-required indicators, candidate setups, configuration fingerprints,
and immutable candidate research runs. Strategy and report CLIs plus real-data
readiness reuse it while retaining their existing arguments, output, defaults,
errors, and storage responsibilities.

Dependency-boundary tests prevent domain packages from importing workflows or
CLI adapters and prevent the data domain from importing higher research layers,
except for the explicitly documented compatibility shim.

## Main files

```text
research/src/tradepilot/workflows/research_run.py
research/src/tradepilot/workflows/real_data_readiness.py
research/src/tradepilot/strategies/cli.py
research/src/tradepilot/reporting/cli.py
research/tests/test_research_run_workflow.py
research/tests/test_dependency_boundaries.py
```

## Verification

Regression tests compare the old construction with the shared workflow and
assert exact breakout and pullback candidate-report IDs. The Step 4 suite
passed 233 tests with two credential-gated skips; the later Phase 4.5 final
suite passed 234 tests with the same two skips.

## Limitations

The workflow supports the currently approved breakout and pullback
configurations. It is application orchestration, not a general strategy plugin
framework.

## Next step

Finalize developer onboarding, CLI discovery, and backend-readiness guidance.

