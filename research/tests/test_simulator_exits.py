import unittest
from datetime import timedelta
from decimal import Decimal

from simulator_helpers import build_context, candle
from tradepilot.backtesting.simulation_models import AuditKind
from tradepilot.backtesting.simulator import EventDrivenSimulator


def exit_reason(result):
    closed = [event for event in result.audit_log if event.kind is AuditKind.POSITION_CLOSED]
    return dict((item.name, item.value) for item in closed[-1].details)["reason"]


class SimulatorExitTests(unittest.TestCase):
    def test_same_candle_stop_and_ambiguity_are_evaluated_after_entry(self) -> None:
        candles = (
            candle(0, bid_high="1.50000", bid_low="0.50000"),
            candle(1, bid_high="1.10300", bid_low="1.09700"),
            candle(2),
        )
        result = EventDrivenSimulator().run(*build_context(
            candles=candles, stop_pips="10", target_pips="10",
        ))
        self.assertEqual(exit_reason(result), "STOP_LOSS")
        ambiguity = [event for event in result.audit_log if event.kind is AuditKind.INTRABAR_AMBIGUITY]
        self.assertEqual(len(ambiguity), 1)
        # The detection candle's extreme range did not close a position before it existed.
        self.assertEqual(result.fills[1].filled_at, candles[1].timestamp + timedelta(hours=1))

    def test_gap_through_stop_uses_worse_opening_quote(self) -> None:
        candles = (
            candle(0),
            candle(1, bid_high="1.10100", bid_low="1.09950"),
            candle(2, bid_open="1.09500", bid_high="1.09600", bid_low="1.09400", bid_close="1.09550"),
        )
        result = EventDrivenSimulator().run(*build_context(
            candles=candles, stop_pips="20", slippage_pips="1", holding=5,
        ))
        exit_fill = result.fills[-1]
        self.assertEqual(exit_reason(result), "STOP_LOSS")
        self.assertEqual(exit_fill.quoted_price, Decimal("1.09500"))
        self.assertEqual(exit_fill.execution_price, Decimal("1.09490"))

    def test_intrabar_target_uses_configured_level_and_protective_precedes_time_exit(self) -> None:
        candles = (
            candle(0),
            candle(1, bid_high="1.10300", bid_low="1.09950"),
            candle(2),
        )
        result = EventDrivenSimulator().run(*build_context(
            candles=candles, target_pips="10", slippage_pips="1", holding=1,
        ))
        self.assertEqual(exit_reason(result), "TAKE_PROFIT")
        self.assertEqual(result.fills[-1].trigger_level, Decimal("1.10130"))
        self.assertEqual(result.fills[-1].execution_price, Decimal("1.10120"))

    def test_opening_target_has_no_favorable_improvement(self) -> None:
        candles = (
            candle(0),
            candle(1, bid_high="1.10100", bid_low="1.09950"),
            candle(2, bid_open="1.11000", bid_high="1.11100", bid_low="1.10900", bid_close="1.11050"),
        )
        result = EventDrivenSimulator().run(*build_context(
            candles=candles, target_pips="20", slippage_pips="1", holding=5,
        ))
        exit_fill = result.fills[-1]
        self.assertEqual(exit_reason(result), "TAKE_PROFIT")
        self.assertEqual(exit_fill.trigger_level, Decimal("1.10230"))
        self.assertEqual(exit_fill.execution_price, Decimal("1.10220"))
        self.assertLess(exit_fill.execution_price, exit_fill.quoted_price)

    def test_time_exit_is_distinct_from_end_of_data_exit(self) -> None:
        timed = EventDrivenSimulator().run(*build_context(holding=1))
        terminal = EventDrivenSimulator().run(*build_context(holding=10))
        self.assertEqual(exit_reason(timed), "TIME_EXIT")
        self.assertEqual(exit_reason(terminal), "END_OF_DATA_EXIT")

    def test_carried_position_exits_before_competing_entry_at_same_open(self) -> None:
        from simulator_helpers import setup
        candles = (
            candle(0), candle(1),
            candle(2, bid_open="1.11000", bid_high="1.11100", bid_low="1.10900", bid_close="1.11050"),
        )
        result = EventDrivenSimulator().run(*build_context(
            candles=candles, signals=(setup(0), setup(1)), target_pips="20", holding=10,
        ))
        at = candles[2].timestamp
        fill_kinds = [
            event.kind for event in result.audit_log
            if event.occurred_at == at and event.kind in (AuditKind.EXIT_FILL, AuditKind.ENTRY_FILL)
        ]
        self.assertEqual(fill_kinds, [AuditKind.EXIT_FILL, AuditKind.ENTRY_FILL])


if __name__ == "__main__":
    unittest.main()
