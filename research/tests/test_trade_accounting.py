import unittest
from dataclasses import replace
from decimal import Decimal

from accounting_helpers import accounting_context
from tradepilot.accounting.engine import build_accounting
from tradepilot.accounting.trades import TradeReconstructionError
from tradepilot.backtesting.policies import CommissionModel, TransactionCostPolicy
from tradepilot.backtesting.simulation_models import SimulationConfig
from tradepilot.backtesting.simulator import EventDrivenSimulator
from simulator_helpers import build_context, setup
from tradepilot.strategies.models import Direction
from tradepilot.accounting.models import MetricStatus


class TradeAccountingTests(unittest.TestCase):
    def test_long_and_short_quote_pnl_formulas(self) -> None:
        for direction, formula_sign in ((Direction.LONG, 1), (Direction.SHORT, -1)):
            integrity, report, simulation, calendar = build_context(
                signals=(setup(direction=direction),), holding=1,
            )
            result = EventDrivenSimulator().run(integrity, report, simulation, calendar)
            config = accounting_context()[2]
            trade = build_accounting(result, simulation, config).content.trades[0]
            expected = (
                (trade.exit_price - trade.entry_price) * trade.quantity_base
                if formula_sign == 1 else
                (trade.entry_price - trade.exit_price) * trade.quantity_base
            )
            self.assertEqual(trade.gross_pnl_quote, expected)

    def test_commissions_are_deducted_once_and_spread_slippage_not_recharged(self) -> None:
        integrity, report, simulation, calendar = build_context(holding=1, spread_pips="2", slippage_pips="1")
        cost = TransactionCostPolicy("1", CommissionModel.FIXED, Decimal("2"))
        simulation = SimulationConfig(replace(simulation.backtest, cost_policy=cost), simulation.signal_order)
        result = EventDrivenSimulator().run(integrity, report, simulation, calendar)
        config = accounting_context()[2]
        report_value = build_accounting(result, simulation, config)
        trade = report_value.content.trades[0]
        self.assertEqual(trade.net_pnl_account, trade.gross_pnl_account - Decimal("4"))
        commission_entries = [item for item in report_value.content.ledger if "COMMISSION" in item.kind.value]
        self.assertEqual(len(commission_entries), 2)

    def test_missing_stop_has_undefined_r_multiple(self) -> None:
        result, simulation, config = accounting_context(holding=1)
        trade = build_accounting(result, simulation, config).content.trades[0]
        self.assertIsNone(trade.r_multiple.value)

    def test_valid_stop_produces_r_multiple_and_terminal_exit_is_labeled(self) -> None:
        result, simulation, config = accounting_context(stop_pips="10", holding=10)
        trade = build_accounting(result, simulation, config).content.trades[0]
        self.assertIs(trade.r_multiple.status, MetricStatus.DEFINED)
        self.assertEqual(trade.r_multiple.value, trade.net_pnl_account / trade.initial_risk_account)
        # The default range reaches the stop; a no-protection run exercises terminal labeling.
        terminal_result, terminal_simulation, terminal_config = accounting_context(holding=10)
        terminal = build_accounting(terminal_result, terminal_simulation, terminal_config).content.trades[0]
        self.assertTrue(terminal.forced_end_of_dataset)

    def test_partial_fill_quantity_is_rejected(self) -> None:
        result, simulation, config = accounting_context(holding=1)
        fills = list(result.fills)
        fills[-1] = replace(fills[-1], quantity=Decimal("5000"))
        broken = replace(result, fills=tuple(fills))
        with self.assertRaisesRegex(TradeReconstructionError, "quantity"):
            build_accounting(broken, simulation, config)


if __name__ == "__main__":
    unittest.main()
