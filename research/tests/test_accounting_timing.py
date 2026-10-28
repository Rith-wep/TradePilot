import unittest

from accounting_helpers import accounting_context
from tradepilot.accounting.engine import build_accounting
from tradepilot.accounting.models import ExecutionTimeKind
from simulator_helpers import candle


class AccountingTimingTests(unittest.TestCase):
    def test_intrabar_exit_preserves_unknown_interval(self) -> None:
        result, simulation, config = accounting_context(
            candles=(candle(0), candle(1, bid_high="1.10300", bid_low="1.09950"), candle(2)),
            target_pips="10", holding=5,
        )
        trade = build_accounting(result, simulation, config).content.trades[0]
        self.assertIs(trade.exit_timing.kind, ExecutionTimeKind.INTRABAR_INTERVAL_UNKNOWN)
        self.assertIsNone(trade.exit_timing.historical_execution_at)
        self.assertLess(trade.exit_timing.interval_start, trade.exit_timing.interval_end)

    def test_time_exit_is_modeled_close_boundary(self) -> None:
        result, simulation, config = accounting_context(holding=1)
        trade = build_accounting(result, simulation, config).content.trades[0]
        self.assertIs(trade.exit_timing.kind, ExecutionTimeKind.CANDLE_CLOSE_BOUNDARY_MODELED)


if __name__ == "__main__":
    unittest.main()
