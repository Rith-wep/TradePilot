import unittest
from dataclasses import replace
from decimal import Decimal

from accounting_helpers import accounting_context
from tradepilot.accounting.engine import build_accounting
from simulator_helpers import build_context, candle, setup
from tradepilot.backtesting.policies import CommissionModel, TransactionCostPolicy
from tradepilot.backtesting.simulation_models import SimulationConfig
from tradepilot.backtesting.simulator import EventDrivenSimulator


class AccountingLedgerTests(unittest.TestCase):
    def test_closed_position_cash_equity_reconcile(self) -> None:
        result, simulation, config = accounting_context(holding=1)
        report = build_accounting(result, simulation, config).content
        final = report.equity_curve[-1]
        self.assertEqual(final.cash + final.unrealized_pnl, final.equity)
        self.assertEqual(final.unrealized_pnl, Decimal("0"))
        self.assertEqual(final.cash, config.initial_balance + report.metrics.net_pnl)

    def test_open_position_is_marked_once_without_recharging_entry_commission(self) -> None:
        result, simulation, config = accounting_context(
            candles=(candle(0), candle(1), candle(3)), holding=10,
        )
        report = build_accounting(result, simulation, config).content
        final = report.equity_curve[-1]
        self.assertNotEqual(final.unrealized_pnl, Decimal("0"))
        self.assertEqual(final.cash + final.unrealized_pnl, final.equity)

    def test_one_final_snapshot_per_timestamp(self) -> None:
        result, simulation, config = accounting_context(holding=1)
        curve = build_accounting(result, simulation, config).content.equity_curve
        self.assertEqual(len({item.timestamp for item in curve}), len(curve))

    def test_exit_and_new_entry_commissions_remain_separate_at_same_timestamp(self) -> None:
        candles = (
            candle(0), candle(1),
            candle(2, bid_open="1.11000", bid_high="1.11100", bid_low="1.10900", bid_close="1.11050"),
        )
        integrity, source, simulation, calendar = build_context(
            candles=candles, signals=(setup(0), setup(1)), target_pips="20", holding=10,
        )
        simulation = SimulationConfig(
            replace(simulation.backtest, cost_policy=TransactionCostPolicy("1", CommissionModel.FIXED, Decimal("2"))),
            simulation.signal_order,
        )
        result = EventDrivenSimulator().run(integrity, source, simulation, calendar)
        config = accounting_context()[2]
        report = build_accounting(result, simulation, config).content
        at = candles[2].timestamp
        kinds = [item.kind.value for item in report.ledger if item.recognized_at == at]
        self.assertEqual(kinds, ["EXIT_GROSS_PNL", "EXIT_COMMISSION", "ENTRY_COMMISSION"])
        self.assertEqual(report.equity_curve[-1].cash + report.equity_curve[-1].unrealized_pnl, report.equity_curve[-1].equity)


if __name__ == "__main__":
    unittest.main()
