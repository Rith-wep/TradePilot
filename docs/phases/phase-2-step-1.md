# Phase 2, Step 1: Technical Indicator Engine

**Status:** Complete  
**Scope:** Deterministic EMA, Wilder RSI, and Wilder ATR calculations over
completed canonical candles.

## Goal

Provide independently testable technical indicators before implementing any
trading strategy. Indicator results describe synthetic price transformations;
they are not evidence of profitability or trading signals.

## What was implemented

- Immutable typed `IndicatorPoint` and `IndicatorSeries` results.
- EMA with simple-average initialization and standard exponential smoothing.
- RSI with Wilder initialization and recursive smoothing.
- ATR with canonical true range and Wilder smoothing.
- Bid, ask, and arithmetic midpoint price-basis selection.
- Aligned `None` warm-up values instead of dropped timestamps.
- Strict period, basis, candle, instrument, timeframe, and Decimal validation.
- Fixed local Decimal precision for reproducible calculations.
- A `tradepilot-indicators` CLI that verifies an immutable snapshot before
  calculating indicators.
- Tests for reference values, warm-up, constants, invalid input, determinism,
  price basis, corrupt datasets, and future-data leakage.

## Architecture

```text
immutable dataset snapshot
          |
          v
Step 3 integrity verification       (CLI boundary only)
          |
          v
validated completed Candle sequence
          |
          v
pure EMA / RSI / ATR functions      (no storage or provider imports)
          |
          v
timestamp-aligned IndicatorSeries
```

The pure calculation module depends on canonical candle models and validation.
The CLI handles snapshot loading and integrity verification.

## Calculation conventions

### EMA

- Input: selected candle close.
- Warm-up: `period - 1` unavailable points.
- Seed: arithmetic mean of the first `period` closes.
- Recurrence: `EMA = alpha × close + (1 - alpha) × previous EMA`, where
  `alpha = 2 / (period + 1)`.

### RSI

- Input: selected candle close changes.
- Warm-up: `period` unavailable points; `period + 1` candles are required.
- Seed: arithmetic means of the first `period` gains and losses.
- Recurrence: `(previous average × (period - 1) + current value) / period`.
- Zero average loss with positive gain returns 100.
- Zero gain and zero loss returns neutral RSI 50.

### ATR

- Input: selected high, low, current close, and previous close.
- True range: maximum of `high-low`, `|high-previous close|`, and
  `|low-previous close|`.
- Warm-up: `period - 1` unavailable points.
- Seed: arithmetic mean of the first `period` true ranges.
- Recurrence: Wilder smoothing, identical in form to RSI averages.

## Price basis and missing data

- `bid` uses canonical bid OHLC.
- `ask` uses canonical ask OHLC.
- `mid` averages corresponding bid and ask OHLC fields. It is analytical and
  not an executable market price. Averaged high/low values may not equal a true
  independently sampled midpoint candle because bid and ask extrema can occur
  at different times.
- Missing candles are never generated. Smoothing continues across observed
  candles, so callers must use the session-aware dataset audit when continuity
  is required.

## Look-ahead protection

Each loop processes candles in chronological order and updates state only after
reading the current candle. No output reads later candles. Automated tests
calculate every prefix independently and verify that it exactly equals the same
prefix of the full-series result.

## Commands

From `research/`:

```powershell
python -m pip install -e .
python -m unittest discover -s tests -v

tradepilot-indicators data/mock/EURUSD/H1 `
  --ema-period 3 `
  --rsi-period 3 `
  --atr-period 3 `
  --price-basis mid
```

## Actual synthetic example

Using the five-candle immutable fixture snapshot, the final timestamp
`2024-01-02T04:00:00Z` produced:

```text
EMA(3, mid): 1.10095000
RSI(3, mid): 62.66666666666666666666666666666667
ATR(3, mid): 0.001581481481481481481481481481481481
```

These values only demonstrate deterministic calculations on synthetic data.
They are not strategy performance or a trading recommendation.

## Verification result

```text
Ran 55 tests in 0.457s
OK

INGEST_EXIT=0
INDICATOR_EXIT=0
```

The original 42 Phase 1 tests remain included and passing.

## Main files

```text
research/src/tradepilot/indicators/__init__.py
research/src/tradepilot/indicators/models.py
research/src/tradepilot/indicators/core.py
research/src/tradepilot/indicators/cli.py
research/tests/test_indicators.py
research/tests/test_indicator_cli.py
research/pyproject.toml
research/README.md
```

## Limitations

- Only canonical H1 candles are currently accepted by the shared validator.
- Midpoint OHLC is derived from bid/ask fields rather than independently
  sampled midpoint ticks.
- Missing intervals do not reset smoothing.
- Values retain raw Decimal precision; display rounding is not part of the
  calculation engine.
- No incremental streaming indicator state is implemented.
- No indicators have been connected to strategy rules.

## Next step

Review the indicator formulas and conventions. Do not implement breakout or
EMA/RSI strategy rules until explicitly approved.
