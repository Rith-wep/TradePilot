# Phase 2, Step 2: Deterministic Trading Strategy Engine

**Status:** Complete  
**Scope:** Price Range Breakout v1 and EMA/RSI Trend Pullback v1 candidate
detection only.

## Goal

Detect reproducible candidate setups from completed synthetic H1 candles and
aligned indicators. This step does not implement backtesting, entries, fills,
orders, risk sizing, profit calculations, or trading recommendations.

## Architecture

```text
immutable dataset snapshot
          |
          v
integrity + candle + session-gap validation
          |
          v
timestamp-aligned indicator series
          |
          v
TradingStrategy protocol
   |                 |
   v                 v
Breakout v1     Pullback v1
   |                 |
   +--------+--------+
            v
immutable SetupRecord candidates
```

Provider and storage logic remain outside the pure strategy implementations.
The CLI loads a verified dataset and calculates the required indicators.

## Immutable setup records

Each record contains strategy/version, instrument, timeframe, direction,
detection candle opening time, completed-candle observability time, rule
evidence, indicator values, invalidation descriptions, configuration
fingerprint, and `structural_invalidation_reference`.

The structural reference is non-executable research metadata. It is not a
stop-loss order, entry instruction, or assumed fill.

## Price Range Breakout v1

Defaults:

```text
lookback: 20
price basis: mid
ATR period: 14
minimum breakout ATR: disabled
reject unexpected gaps: true
```

For completed candle `t`, only `[t-N, ..., t-1]` defines the range:

```text
range_high = max(high[t-N], ..., high[t-1])
range_low  = min(low[t-N], ..., low[t-1])

LONG:  close[t] > range_high
SHORT: close[t] < range_low
```

Equality does not trigger. The current candle is excluded. An optional ATR
filter requires breakout distance to be at least `multiplier × ATR[t]`.
The structural reference is the broken range boundary.

## EMA/RSI Trend Pullback v1

Defaults:

```text
EMA period: 200
RSI period: 14
ATR period: 14
RSI recovery level: 50
price basis: mid
reject unexpected gaps: true
```

LONG requires:

```text
EMA[t] > EMA[t-1]
close[t-1] <= EMA[t-1]
close[t] > EMA[t]
RSI[t] > 50
RSI[t] > RSI[t-1]
```

SHORT requires:

```text
EMA[t] < EMA[t-1]
close[t-1] >= EMA[t-1]
close[t] < EMA[t]
RSI[t] < 50
RSI[t] < RSI[t-1]
```

The previous candle must be on the opposite side of the EMA, requiring a fresh
recovery crossover. Consecutive candles remaining above or below the EMA do not
repeatedly trigger.

```text
LONG structural reference:  low[t-1] - ATR[t]
SHORT structural reference: high[t-1] + ATR[t]
```

## Causality

Canonical timestamps are candle opening times. For H1 candle `t`:

```text
detection_candle_open_time = t
observable_at = t + 1 hour
```

A setup is never available at its opening time, and no entry price is assigned.
Indicator timestamps must match candles exactly. Warm-up values suppress
detection. Prefix-invariance tests run every historical prefix and verify that
future candles never alter earlier candidates.

## Gaps, fingerprints, and duplicates

The configurable session calendar allows expected closures. Unexpected missing
H1 intervals reject detection by default, and no candles are fabricated.

Configuration fingerprints are SHA-256 hashes of canonical strategy name,
version, parameters, price basis, gap policy, and calendar identity.

Duplicate identity is:

```text
strategy + version + instrument + timeframe + direction + detection timestamp
```

Identical duplicates collapse deterministically; conflicts raise an error.

## Commands

```powershell
cd research
python -m pip install -e .
python -m unittest discover -s tests -v

tradepilot-strategy data/mock/EURUSD/H1 breakout --lookback 20

tradepilot-strategy data/mock/EURUSD/H1 pullback `
  --ema-period 200 --rsi-period 14 --atr-period 14
```

## Tests

The suite covers LONG/SHORT breakouts, equality, current-candle exclusion,
optional ATR filtering, fresh LONG/SHORT pullbacks, consecutive-signal
prevention, warm-up, misalignment, invalid configuration, insufficient history,
unexpected gaps, duplicate prevention, opening versus observable timestamps,
configuration fingerprints, repeated execution, prefix invariance, CLI
integrity checks, and absence of performance metrics.

It also includes a regression test ensuring Decimal values such as `12.5` and
`12.50000` preserve the same canonical dataset identity after Parquet storage.

Final verification:

```text
Ran 79 tests in 0.970s
OK

TEST_EXIT=0
INGEST_EXIT=0
STRATEGY_EXIT=0
```

The installed CLI detected this candidate in the immutable five-candle
synthetic fixture when run with breakout lookback 2:

```text
Strategy: price_range_breakout@1.0.0
Direction: SHORT
Detection candle open: 2024-01-02T03:00:00Z
Observable at: 2024-01-02T04:00:00Z
Structural invalidation reference: 1.100275
```

Dedicated crossover fixtures also produced:

```text
LONG pullback:  open 2024-01-01T02:00:00Z, observable 03:00:00Z, reference 97
SHORT pullback: open 2024-01-01T02:00:00Z, observable 03:00:00Z, reference 103
```

All examples are synthetic rule demonstrations, not trading recommendations or
performance evidence.

## Main files

```text
research/src/tradepilot/strategies/__init__.py
research/src/tradepilot/strategies/models.py
research/src/tradepilot/strategies/base.py
research/src/tradepilot/strategies/breakout.py
research/src/tradepilot/strategies/pullback.py
research/src/tradepilot/strategies/cli.py
research/tests/strategy_helpers.py
research/tests/test_breakout_strategy.py
research/tests/test_pullback_strategy.py
research/tests/test_strategy_validation.py
research/tests/test_strategy_cli.py
```

## Limitations

- These are unvalidated hypotheses, not profitable systems.
- Only H1 candle observability is implemented.
- Unexpected-gap rejection is dataset-wide and conservative.
- Midpoint OHLC is an arithmetic bid/ask approximation.
- Structural references do not model executable orders or fills.
- There is no expiry or ongoing setup-state machine.
- No optimization, backtesting, or parameter fitting was performed.

## Next step

Review the exact rules and setup records. Do not begin backtesting or another
strategy step without explicit approval.
