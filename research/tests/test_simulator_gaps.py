import unittest
from datetime import datetime, timezone

from simulator_helpers import START, build_context, candle, setup
from tradepilot.backtesting.simulation_models import AuditKind
from tradepilot.backtesting.simulator import EventDrivenSimulator
from tradepilot.data.sessions import WeeklySessionCalendar


class SimulatorGapTests(unittest.TestCase):
    def test_dataset_end_before_expiry_is_unresolved_and_order_stays_pending(self) -> None:
        result = EventDrivenSimulator().run(*build_context(candles=(candle(0),), expiry_hours=5))
        self.assertEqual(result.order_states[0][1].value, "PENDING")
        unresolved = [event for event in result.audit_log if event.kind is AuditKind.UNRESOLVED_END_OF_DATA]
        self.assertEqual(len(unresolved), 1)
        self.assertEqual(unresolved[0].occurred_at, START.replace(hour=11))

    def test_unexpected_weekday_gap_rejects_pending_order(self) -> None:
        result = EventDrivenSimulator().run(*build_context(
            candles=(candle(0), candle(2)), expiry_hours=4,
        ))
        self.assertEqual(result.order_states[0][1].value, "REJECTED")

    def test_expected_weekend_closure_can_be_skipped_before_expiry(self) -> None:
        # Friday 21:00 and Sunday 22:00 in the default UTC FX calendar.
        from simulator_helpers import DATA_INSTRUMENT
        from tradepilot.data.models import Candle
        from decimal import Decimal
        friday = datetime(2024, 1, 5, 21, tzinfo=timezone.utc)
        def at(value):
            return Candle(DATA_INSTRUMENT, value, "H1", *(Decimal(x) for x in (
                "1.1", "1.101", "1.099", "1.1", "1.1002", "1.1012", "1.0992", "1.1002"
            )), "synthetic", "v1", True)
        candles = (at(friday), at(datetime(2024, 1, 7, 22, tzinfo=timezone.utc)))
        signal = setup()
        signal = signal.__class__(
            signal.strategy_name, signal.strategy_version, signal.instrument, signal.timeframe,
            friday, friday.replace(hour=22), signal.direction, signal.setup_type,
            signal.indicator_values, signal.rule_evidence, signal.invalidation_conditions,
            signal.structural_invalidation_reference, signal.configuration_fingerprint,
        )
        calendar = WeeklySessionCalendar(name="simulation-calendar")
        result = EventDrivenSimulator().run(*build_context(
            candles=candles, signals=(signal,), expiry_hours=72, calendar=calendar,
        ))
        self.assertTrue(any(event.kind is AuditKind.EXPECTED_CLOSURE_SKIPPED for event in result.audit_log))
        self.assertTrue(result.fills)


if __name__ == "__main__":
    unittest.main()
