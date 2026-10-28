import unittest
from datetime import timedelta
from decimal import Decimal

from simulator_helpers import START, build_context, candle, setup
from tradepilot.backtesting.events import PriceSide
from tradepilot.backtesting.simulation_models import AuditKind
from tradepilot.backtesting.simulator import EventDrivenSimulator
from tradepilot.strategies.models import Direction


class SimulatorEntryTests(unittest.TestCase):
    def test_long_and_short_entries_use_correct_sides_and_costs(self) -> None:
        for direction, expected_side, expected_raw, expected_final in (
            (Direction.LONG, PriceSide.ASK, Decimal("1.10020"), Decimal("1.10040")),
            (Direction.SHORT, PriceSide.BID, Decimal("1.10000"), Decimal("1.09980")),
        ):
            context = build_context(
                signals=(setup(direction=direction),), spread_pips="2", slippage_pips="1",
            )
            result = EventDrivenSimulator().run(*context)
            entry = next(fill for fill in result.fills if fill.purpose.value == "ENTRY")
            self.assertEqual((entry.price_side, entry.quoted_price, entry.execution_price), (expected_side, expected_raw, expected_final))
            self.assertIsNotNone(entry.stressed_price)

    def test_equal_timestamp_order_and_no_detection_open_entry(self) -> None:
        result = EventDrivenSimulator().run(*build_context())
        boundary = START + timedelta(hours=1)
        kinds = [event.kind for event in result.audit_log if event.occurred_at == boundary]
        self.assertLess(kinds.index(AuditKind.MARKET_CANDLE_COMPLETED), kinds.index(AuditKind.SIGNAL_CONSIDERED))
        self.assertLess(kinds.index(AuditKind.SIGNAL_CONSIDERED), kinds.index(AuditKind.MARKET_OPENING_QUOTE))
        entry = next(fill for fill in result.fills if fill.purpose.value == "ENTRY")
        self.assertEqual(entry.filled_at, boundary)
        self.assertNotEqual(entry.filled_at, START)

    def test_expiry_exactly_at_opening_quote_rejects_fill(self) -> None:
        # Signal at 11:00, the next actual candle opens at 12:00, exactly at expiry.
        class ExpectedClosureCalendar:
            calendar_id = "expected-one-hour-closure"

            def is_expected_open(self, timestamp):
                return timestamp != START + timedelta(hours=1)

        calendar = ExpectedClosureCalendar()
        context = build_context(
            candles=(candle(0), candle(2)), expiry_hours=1, calendar=calendar,
        )
        result = EventDrivenSimulator().run(*context)
        self.assertFalse(result.fills)
        self.assertEqual(result.order_states[0][1].value, "EXPIRED")

    def test_competing_signals_are_deterministic(self) -> None:
        opposing = build_context(signals=(setup(direction=Direction.LONG), setup(direction=Direction.SHORT)))
        result = EventDrivenSimulator().run(*opposing)
        self.assertFalse(result.orders)
        same = build_context(signals=(setup(direction=Direction.LONG), setup(direction=Direction.LONG)))
        same_result = EventDrivenSimulator().run(*same)
        self.assertEqual(len(same_result.orders), 1)

    def test_future_entry_candle_extrema_cannot_change_opening_fill(self) -> None:
        calm = build_context(candles=(candle(0), candle(1), candle(2)))
        volatile = build_context(candles=(
            candle(0),
            candle(1, bid_high="1.50000", bid_low="0.50000", bid_close="1.40000"),
            candle(2),
        ))
        calm_entry = EventDrivenSimulator().run(*calm).fills[0]
        volatile_entry = EventDrivenSimulator().run(*volatile).fills[0]
        self.assertEqual(
            (calm_entry.filled_at, calm_entry.quoted_price, calm_entry.execution_price),
            (volatile_entry.filled_at, volatile_entry.quoted_price, volatile_entry.execution_price),
        )


if __name__ == "__main__":
    unittest.main()
