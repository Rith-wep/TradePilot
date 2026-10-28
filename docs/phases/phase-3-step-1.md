# Phase 3, Step 1: Backtesting Architecture and Domain Models

**Status:** Complete  
**Scope:** Immutable domain records and validation only. There is no simulation
loop, order matching, P&L calculation, or performance reporting.

## Architecture

```text
verified immutable dataset -----------+
                                       |
immutable candidate research report --+--> BacktestConfig
                                                |
             +----------------------------------+------------------+
             |                                  |                  |
      market events                       order events        policy records
   (open vs completed)                  (state history)      (cost/risk/etc.)
             |                                  |
             +---------------------------> fill facts
                                                |
                                         position states
```

The package consumes dataset and report provenance without changing either
artifact. All domain records are frozen dataclasses with slots.

## Configuration and provenance

`BacktestConfig` records dataset ID/checksum, research report ID, strategy and
configuration identity, implementation revision, instrument, timeframe,
session calendar, account currency, execution-model version, and every policy.
Its canonical SHA-256 identity excludes the separate `BacktestRun.created_at`.

Validation recomputes the research report ID and checks it against the verified
dataset, strategy, instrument, timeframe, and configuration fingerprint.

## Event timeline and information availability

For an H1 detection candle opening at 10:00 UTC:

```text
10:00                         11:00 boundary
  |                                  |
  | detection opening quote          | 1. completed 10:00 candle available
  | exposes bid/ask open only        | 2. setup becomes observable
  |                                  | 3. 11:00 opening quote available
  |                                  |    and may execute an eligible order
```

Equal-timestamp order is `CANDLE_COMPLETED`, `SIGNAL_OBSERVABLE`, then
`OPENING_QUOTE`. `OpeningQuoteEvent` contains no high, low, or close fields.
`CompletedCandleEvent` exposes full OHLC only at H1 close. Entry pricing accepts
only opening events, so future candle extrema cannot affect entry decisions.
The detection candle's opening quote is never eligible.

## Orders and expiry

Only `MARKET_NEXT_ELIGIBLE_OPEN` is supported. Each request has an explicit
expiry later than its earliest execution timestamp.

```text
CREATED --> PENDING --> FILLED
   |           |------> REJECTED
   |           |------> CANCELLED
   |           `------> EXPIRED
   |----------> REJECTED
   `----------> CANCELLED
```

Terminal states have no outgoing transitions. Expected session closures may be
skipped only while an order remains valid. No eligible quote before expiry
means `EXPIRED`; an unexpected gap uses strict rejection. No missing candle or
quote is fabricated. A position can be created only from a validated entry fill
for a pending order.

## Execution conventions

| Action | Quote side |
| --- | --- |
| LONG entry | ask |
| LONG exit | bid |
| SHORT entry | bid |
| SHORT exit | ask |

Observed bid/ask already includes spread. Extra stress widens it without
charging the base spread twice:

```text
stressed ask = quoted ask + additional spread / 2
stressed bid = quoted bid - additional spread / 2
```

Slippage is separate and adverse: buys increase and sells decrease.

Structural invalidation references remain non-executable research facts. Stops
and targets are optional explicit values: LONG stop below entry and target
above; SHORT stop above and target below.

Future stop/target processing must check the executable opening side before
intrabar extrema. A gap-through stop uses the adverse executable open. A target
crossed at open also uses the executable open. Conservative stop-first applies
only when both levels are intrabar-reachable and ordering is unknowable; it is
an uncertainty convention, not reconstructed history. Lower-timeframe ordering
requires separately verified reliable data.

## Currency conversion

Instrument metadata records base/quote currencies, pip size, precision, and
quantity increment. Different instruments are not assigned a universal pip
value.

When account and quote currency differ, each relevant financial event requires
a compatible conversion observation containing pair, positive rate, UTC
timestamp, source, dataset ID, and checksum. It must be available no later than
the event. A future rate cannot value earlier history. Conversion arithmetic is
not implemented in this step.

## Explicit policies

- Commission: none, fixed, or per unit.
- Financing: deliberately none, or explicit rates, rollover time, and timezone.
- Risk: one open position and a positive maximum quantity.
- Execution: versioned next-open, strict-gap, spread stress, slippage,
  gap-stop, opening-target, and ambiguity assumptions.

An explicit `NONE` is a deliberate zero assumption, not a missing setting.

## Tests

```powershell
cd research
python -m unittest discover -s tests
```

```text
Ran 122 tests in 1.045s
OK
```

The 25 new tests cover immutability, price/quantity/timestamp validation,
precision, deterministic configuration identity, transitions, expiry,
price-side rules, information leakage, fill timing, position creation,
currency observations, and provenance. All previous 97 tests remain passing.

## Main files

```text
research/src/tradepilot/backtesting/__init__.py
research/src/tradepilot/backtesting/models.py
research/src/tradepilot/backtesting/events.py
research/src/tradepilot/backtesting/orders.py
research/src/tradepilot/backtesting/positions.py
research/src/tradepilot/backtesting/policies.py
research/src/tradepilot/backtesting/config.py
research/src/tradepilot/backtesting/validation.py
research/tests/backtesting_helpers.py
research/tests/test_backtest_models.py
research/tests/test_order_lifecycle.py
research/tests/test_execution_conventions.py
research/tests/test_backtest_validation.py
```

## Limitations

- No event loop, order matching, simulated fill generation, or persistence.
- Gap/session policies are contracts and are not executed yet.
- No stop/target triggering or lower-timeframe reconstruction.
- No cost, financing, conversion, pip-value, position-size, P&L, trade-log, or
  performance calculations.
- H1 is the only supported timeframe; synthetic data is the tested baseline.

## Next step

After explicit approval, build the deterministic event-driven simulator around
these contracts. Do not begin it as part of this step.
