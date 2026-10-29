# Phase 3, Step 4: Chronological Validation and Robustness

**Status:** Complete  
**Scope:** Synthetic, deterministic research validation only. No live trading,
new strategy formulas, or profitability claim.

## Architecture

The provider-neutral `tradepilot.validation` package consumes immutable candle
snapshots, candidate reports, simulator results, and accounting reports. It does
not modify any of them.

```text
verified candles + immutable candidates
              |
       60 / 20 / 20 split
              |
 training grid + expanding walk-forward folds
              |
 five full execution/accounting cost runs
              |
 deterministic selection -> frozen authorization -> locked test
              |
 canonical SHA-256 validation report
```

## Chronological partitions and boundaries

Partitions use eligible candle counts and half-open UTC intervals `[start,end)`.
For 100 candles, indexes are training `[0,60)`, validation `[60,80)`, and
locked test `[80,100)`. Dataset, indexes, timestamps, policy, and name enter
each partition ID.

Strategies may receive the complete historical prefix needed for recursive
indicator warm-up. Only candidates whose detection opening and observable time
both lie in the active partition are eligible. A final-candle candidate that
becomes observable exactly at the following boundary is excluded. Candles,
orders, entries, pending orders, and positions cannot cross the boundary. The
existing terminal-close and unresolved-order conventions apply at that local
research boundary.

## Compatible parameter grid

The existing strategy interfaces were inspected before declaring this grid:

- Price Range Breakout v1: lookback 10, 20, or 40;
- EMA/RSI Trend Pullback v1: EMA period 100 or 200.

Both fields were already configurable. Existing defaults, strategy versions,
formulas, RSI rules, crossover rules, and fingerprints remain unchanged. The
grid deliberately does not vary stops, targets, RSI, indicators, or execution.

## Walk-forward and selection

Walk-forward folds use expanding training prefixes and non-overlapping
validation windows. A step smaller than the validation window is rejected.
Every fold is retained, including zero-trade and insufficient-sample folds.

The default thresholds are 10 trades per fold and 30 trades for top-level
training and validation. A configuration must satisfy the threshold under every
cost scenario before ranking. Ranking is deterministic:

1. highest worst-scenario validation expectancy;
2. lowest worst-scenario maximum drawdown;
3. highest minimum scenario trade count;
4. lexicographically smallest configuration fingerprint.

Rejected configurations and reasons remain in the decision. This heuristic is
not evidence of a trading edge, and locked-test results are rejected by the
selection API.

## Cost stress and robustness

Five scenarios are declared: baseline, +1 pip incremental spread, +1 pip
adverse slippage, 2x commission, and the combined adverse case. Each scenario
reruns the event simulator and accounting engine. Historical bid/ask spread is
preserved; spread stress is incremental. P&amp;L is never adjusted after the run.

Robustness output includes positive-fold fraction, zero/insufficient folds,
median and range of fold expectancy, scenario degradation, forced terminal
exit count, and ambiguous exit count. Those trades remain in financial metrics
and are separately disclosed as research assumptions.

## Bootstrap uncertainty

Moving-block bootstrap uses circular five-trade blocks, 1,000 resamples, a
SHA-256-derived deterministic random seed, and a 30-trade minimum. Smaller
samples return `INSUFFICIENT_SAMPLE` with no interval. The interval is a
descriptive uncertainty estimate, not statistical proof or a significance test.

## Locked-test governance

Authorization freezes dataset ID/checksum, locked partition, strategy/version,
selected configuration, selection decision, cost-scenario identities, and
implementation revision. Its canonical content is verified before publication.
The registry permits identical result retrieval and rejects conflicting
replacement or tampered authorization.

Enforcement is process-scoped. No filesystem authorization store is included,
so deterministic IDs alone do not guarantee that a human evaluates a locked
test only once.

## Reproducibility

Frozen dataclasses and exact Decimal values are serialized by the existing
canonical JSON encoder. SHA-256 identifies partitions, folds, cost scenarios,
selection decisions, authorizations, and the final validation report. Creation
time is absent from deterministic content.

## Verification

```powershell
cd research
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

The actual full-suite result is recorded after final verification in the task
handoff.

## Main files

```text
research/src/tradepilot/validation/models.py
research/src/tradepilot/validation/partitions.py
research/src/tradepilot/validation/warmup.py
research/src/tradepilot/validation/parameters.py
research/src/tradepilot/validation/walk_forward.py
research/src/tradepilot/validation/stress.py
research/src/tradepilot/validation/robustness.py
research/src/tradepilot/validation/uncertainty.py
research/src/tradepilot/validation/governance.py
research/src/tradepilot/validation/reporting.py
research/src/tradepilot/validation/engine.py
```

## Limitations and research risks

- Synthetic data only; no claim of real-market performance.
- Small fixed grid; no general optimizer or nested cross-validation.
- Candle OHLC execution ambiguity and terminal closure assumptions remain.
- Bootstrap depends on the chosen block length and observed trade sequence.
- Sample thresholds are policy choices, not guarantees of generalization.
- Locked authorization is not durable across processes.
- No multiple-testing correction, regime model, margin, financing, or live data.

## Next step

Stop here and wait for approval before Phase 4.
