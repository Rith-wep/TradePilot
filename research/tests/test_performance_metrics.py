import unittest
from dataclasses import replace

from accounting_helpers import accounting_context
from tradepilot.accounting.engine import build_accounting
from tradepilot.accounting.models import MetricStatus


class PerformanceMetricTests(unittest.TestCase):
    def test_zero_trade_metrics_and_undefined_profit_factor(self) -> None:
        result, simulation, config = accounting_context()
        empty_result = replace(result, fills=(), positions=(), orders=(), order_states=())
        empty_result = replace(empty_result, audit_log=tuple(
            event for event in result.audit_log
            if event.kind.value.startswith("MARKET_")
        ))
        metrics = build_accounting(empty_result, simulation, config).content.metrics
        self.assertEqual(metrics.closed_trades, 0)
        self.assertIs(metrics.win_rate.status, MetricStatus.UNDEFINED_NO_TRADES)
        self.assertIs(metrics.profit_factor.status, MetricStatus.UNDEFINED_NO_LOSSES)

    def test_drawdown_is_derived_from_equity_curve(self) -> None:
        result, simulation, config = accounting_context(stop_pips="10", holding=5)
        report = build_accounting(result, simulation, config).content
        self.assertEqual(report.metrics.maximum_drawdown, max(item.drawdown_amount for item in report.equity_curve))


if __name__ == "__main__":
    unittest.main()
