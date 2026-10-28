# Phase 3, Step 3: Deterministic Portfolio Accounting and Analytics

**Status:** Complete  
**Scope:** Trade reconstruction, account-currency accounting, ledger, equity,
and descriptive metrics. No execution changes or strategy optimization.

## Architecture

```text
immutable SimulationResult
          |
          +--> execution timing classification
          +--> strict fill/position reconstruction
          +--> historical currency conversion
          +--> event-ordered cash ledger
          +--> timestamp-final equity marks
          +--> trade and portfolio metrics
          |
          v
canonical deterministic accounting report
```

The accounting package consumes recorded fills. It never recalculates execution
prices or subtracts bid/ask spread, spread stress, or slippage again.

## Execution-time honesty

An intrabar H1 stop or target has no known tick timestamp. Its report contains:

- the candle interval in which it is assumed to occur;
- `historical_execution_at = null`;
- the candle-completion `recognized_at` timestamp when the outcome becomes
  knowable to the simulator.

Opening fills use `OPENING_BOUNDARY`. Time and terminal close fills use
`CANDLE_CLOSE_BOUNDARY_MODELED`. Ambiguous intrabar exits remain explicitly
`INTRABAR_AMBIGUOUS`. Financial realization occurs at recognition time, never
at an invented intrabar timestamp.

## Trade formulas

Quantity is base-currency units:

```text
LONG gross quote P&L  = (exit - entry) * quantity
SHORT gross quote P&L = (entry - exit) * quantity

net account P&L = converted gross quote P&L
                  - converted entry commission
                  - converted exit commission
```

Each closed trade requires exactly one entry and one exit fill with matching
order, instrument, direction, and quantity. Duplicates and partial fills are
rejected.

Recorded commissions are posted separately at entry and exit. Since the current
simulator policy has no commission-currency field, `AccountingConfig` must label
its declared commission currency as an explicit assumption. A future source
currency, when present, must match.

Step 2 permits financing `NONE` only, so accounting reports exclude overnight
financing rather than silently estimating it.

## Historical currency conversion

Execution prices and quote-currency P&L remain unchanged. Conversion is applied
only to account-currency values.

```text
direct Q/A:     account amount = quote amount * rate
reciprocal A/Q: account amount = quote amount / rate
```

The converter selects the latest observation at or before the valuation event
within the configured maximum staleness. Future, missing, stale, non-positive,
or conflicting observations are rejected. Used source, timestamp, pair,
orientation, rate, dataset ID, and checksum are retained. Unused observations
do not enter deterministic report content.

## Cash and equity

FX notional is exposure, not an automatic cash debit:

```text
cash = initial balance
       - recognized entry commissions
       + recognized gross closed-trade P&L
       - recognized exit commissions

equity = cash + unrealized P&L
```

LONG positions mark to stressed bid; SHORT positions mark to stressed ask.
Marks exclude hypothetical future slippage and exit commission. Entry commission
is not charged again in unrealized P&L.

Every financial posting remains a separate immutable ledger transaction in
simulation event order. One final equity point is emitted per timestamp after
all events at that timestamp, preserving both an exit commission and a new entry
commission when they coincide.

## Metrics

Trade outcomes use net account-currency P&L after commissions:

- gross profit: sum of positive net trade outcomes;
- gross loss: absolute sum of negative net trade outcomes;
- net P&L: sum of all net closed-trade outcomes;
- expectancy: net P&L divided by closed trades;
- profit factor: gross profit divided by gross loss.

Undefined values retain statuses such as `UNDEFINED_NO_TRADES`,
`UNDEFINED_NO_WINS`, `UNDEFINED_NO_LOSSES`, and
`UNDEFINED_ZERO_INITIAL_RISK`; they are never silently replaced with zero.

R uses price risk excluding commission in the denominator and net P&L including
commission in the numerator. A missing or invalid executable initial stop makes
R undefined. Structural invalidation references are ignored.

Drawdown is calculated from timestamp-final equity:

```text
peak = maximum prior equity
drawdown = peak - current equity
drawdown percentage = drawdown / peak
```

Forced terminal and ambiguous exits remain in financial statistics and are
separately counted. Holding duration is reported as lower and upper bounds when
intrabar time is unknown.

## Reproducibility

Canonical report content records dataset/report/simulation/configuration IDs,
execution and accounting versions, implementation revision, account and
commission currencies, initial balance, used conversions, trades, ledger,
equity, and metrics. SHA-256 over canonical JSON produces the report ID. Run
creation timestamps are separate and do not affect identity.

## Verification

```powershell
cd research
python -m unittest discover -s tests
```

```text
Ran 160 tests in 1.373s
OK
```

All prior 141 tests remain passing. The 19 accounting tests cover LONG/SHORT
P&L, costs, timing uncertainty, direct/reciprocal conversion, missing and stale
rates, open/closed/sequential ledger reconciliation, marks, terminal exits,
R-multiples, zero-trade metrics, undefined profit factor, drawdown,
deterministic identity, provenance, and partial-fill rejection.

## Main files

```text
research/src/tradepilot/accounting/models.py
research/src/tradepilot/accounting/timing.py
research/src/tradepilot/accounting/conversion.py
research/src/tradepilot/accounting/trades.py
research/src/tradepilot/accounting/ledger.py
research/src/tradepilot/accounting/metrics.py
research/src/tradepilot/accounting/reporting.py
research/src/tradepilot/accounting/engine.py
research/tests/accounting_helpers.py
research/tests/test_accounting_timing.py
research/tests/test_trade_accounting.py
research/tests/test_currency_conversion.py
research/tests/test_accounting_ledger.py
research/tests/test_performance_metrics.py
research/tests/test_accounting_reproducibility.py
```

## Limitations

- No margin, leverage limits, liquidation, financing, tax, or broker ledger.
- H1 intrabar execution times and paths remain unknown.
- Partial fills and multiple concurrent positions are unsupported.
- Cross-currency results require supplied verified synthetic observations.
- No confidence intervals, walk-forward analysis, optimization, or claims of
  real-world profitability.
- Accounting reports are returned in memory; immutable filesystem storage is
  not included in this step.

## Next step

Wait for approval before Phase 3, Step 4 robustness work.
