# Phase 3, Step 2: Deterministic Event-Driven Forex Execution Simulator

**Status:** Complete  
**Scope:** Synthetic historical order, fill, and position simulation. No P&L or
portfolio performance metrics.

## Architecture

```text
verified candle snapshot -----+
                              +--> validated configuration --> chronological queue
verified candidate report ----+                              |
                      +---------------------------------------+------------------+
                      |                                       |                  |
               candle completed                        signal observable   opening quote
                      +---------------------------------------+------------------+
                                                              |
                                                    orders/fills/positions
                                                              |
                                                    immutable audit trace
```

Dataset, report, strategy, configuration, instrument, timeframe, calendar, and
checksum provenance must agree. Step 2 rejects financing configurations other
than `FinancingModel.NONE`.

## Event processing and availability

Events sort by UTC timestamp, priority, and deterministic subject key. At an H1
boundary the order is completed previous candle, observable signal, then next
opening quote. Gap and expiry decisions occur before an opening can fill.

```text
10:00  detection candle opens; setup unavailable
11:00  detection candle completes
11:00  setup becomes observable and may create a pending order
11:00  next opening bid/ask may fill it
12:00  entry candle high/low/close become available for protection checks
```

Opening events contain only bid/ask opens. Completed events expose high, low,
and close only at candle close. Altering a future range cannot change the
opening fill. A newly opened position uses only that candle's subsequent range,
never the preceding detection candle's extrema.

## Signal-to-order policy

`SignalOrderPolicy` records quantity, entry expiry, mandatory maximum holding
candles, optional stop/target pip distances, competing-signal handling, and the
end-of-dataset policy. Stops and targets derive from the actual entry fill;
structural invalidation references remain non-executable.

Simultaneous opposing candidates are all rejected. Same-direction ties select
the smallest canonical candidate ID. A pending candidate can wait while a
position is open. At a shared opening, carried-position protection runs before
the pending entry, ensuring at most one open position.

## Entry execution

LONG enters at ask and SHORT enters at bid. Additional spread stress widens the
observed quote; adverse slippage is separate. Every fill preserves raw quote,
stressed quote, execution reference, slippage, final price, and commission.
Quantity increment, precision, timing, expiry, and provenance are validated.

A quote at `expires_at` cannot fill. The detection candle's opening quote also
cannot fill.

## Exit ordering and pricing

For a carried position:

1. stressed executable opening stop;
2. stressed executable opening target;
3. completed-candle intrabar protection;
4. scheduled time exit;
5. final-dataset research exit.

LONG exits use bid and SHORT exits use ask.

- Gap-through stops fill from the worse stressed opening quote plus adverse
  slippage, not from the requested stop.
- Targets crossed at opening receive no favorable improvement: the configured
  target is the execution reference, followed by adverse slippage.
- Intrabar trigger checks use stressed extrema. Fills use configured levels plus
  adverse slippage as a modeling assumption, not an observed tick fill.
- If both levels are reachable and their order is unknown, the log records
  `INTRABAR_AMBIGUITY` and uses `CONSERVATIVE_STOP_FIRST`. This does not claim to
  reconstruct the historical path.

Holding candles count from entry. Protective exits precede a scheduled
`TIME_EXIT`. A surviving position is closed at the final completed executable
close with `END_OF_DATA_EXIT`; this is an explicit research convention.

## Gaps, expiry, and dataset end

The existing session calendar and gap classifier are reused.

- Expected closures can be skipped while an order remains valid.
- Unexpected gaps reject pending execution.
- An unexpected gap crossed by an open position invalidates the simulation.
- Missing candles are never synthesized.
- Expiry inside the available timeline produces `EXPIRED`.
- If history ends first, the order remains `PENDING` and receives
  `UNRESOLVED_END_OF_DATA` at the final known timestamp. No future event or
  timestamp is invented.

## Audit log and reproducibility

Every immutable record contains dataset/report/configuration provenance and a
deterministic SHA-256 ID. Records cover market availability, candidates,
rejections, orders, transitions, fills, positions, triggers, ambiguities, gaps,
expiry, and unresolved terminal orders. Decimal values serialize exactly.

Abbreviated trace:

```text
11:00 MARKET_CANDLE_COMPLETED  detection facts become available
11:00 SIGNAL_CONSIDERED        LONG candidate
11:00 ORDER_CREATED            pending market-at-next-open order
11:00 MARKET_OPENING_QUOTE     bid=1.10000 ask=1.10020
11:00 ENTRY_FILL               LONG ask entry
12:00 MARKET_CANDLE_COMPLETED  entry candle range becomes available
12:00 EXIT_TRIGGER             TAKE_PROFIT at configured level
12:00 EXIT_FILL                LONG bid exit
12:00 POSITION_CLOSED          TAKE_PROFIT
```

## Commands

```powershell
cd research
python -m pip install -e .
python -m unittest discover -s tests

tradepilot-backtest data/mock/EURUSD/H1 reports/{report-id} `
  --quantity 10000 --entry-expiry-hours 72 --max-holding-candles 24 `
  --stop-pips 20 --target-pips 40
```

The CLI prints deterministic JSON with no profitability fields.

## Verification results

```text
Ran 141 tests in 1.193s
OK
```

All 122 pre-existing tests remain passing. The 19 new tests cover entry sides,
stress and slippage, event ordering, future-data isolation, exact expiry,
unresolved dataset-end orders, weekend and unexpected gaps, stop/target exits,
gap stops, conservative opening targets, same-candle ambiguity, carried exits,
time versus terminal exits, competing candidates, financing rejection,
provenance, repeated-run identity, and CLI output.

## Main files

```text
research/src/tradepilot/backtesting/input.py
research/src/tradepilot/backtesting/signal_policy.py
research/src/tradepilot/backtesting/execution.py
research/src/tradepilot/backtesting/simulation_models.py
research/src/tradepilot/backtesting/simulator.py
research/src/tradepilot/backtesting/cli.py
research/tests/simulator_helpers.py
research/tests/test_simulator_entries.py
research/tests/test_simulator_exits.py
research/tests/test_simulator_gaps.py
research/tests/test_simulator_reproducibility.py
research/tests/test_backtest_cli.py
```

## Limitations

- H1 OHLC does not reveal true intrabar paths or tick fills.
- Stop/target fills are documented research assumptions.
- Financing other than explicit `NONE` is rejected.
- No conversion, ledger, P&L, position sizing, performance statistics,
  optimization, result storage, or live execution.
- One instrument, one pending order, and one open position are supported.

## Next step

Wait for approval before result persistence or performance calculations in
Phase 3, Step 3.
