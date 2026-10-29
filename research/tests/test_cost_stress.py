import unittest
from datetime import timedelta
from decimal import Decimal

from simulator_helpers import START, build_context, setup
from tradepilot.accounting.models import AccountingConfig
from tradepilot.validation.models import ChronologicalPartition, PartitionName
from tradepilot.validation.stress import approved_cost_scenarios, run_cost_scenarios


class CostStressTests(unittest.TestCase):
    def test_scenarios_rerun_execution_and_accounting(self) -> None:
        integrity, report, simulation, calendar = build_context(holding=1)
        partition = ChronologicalPartition(
            PartitionName.VALIDATION, START, START + timedelta(hours=3),
            0, 3, 3, "p" * 64,
        )
        accounting = AccountingConfig("USD", Decimal("10000"), "USD", True, timedelta(hours=24))
        results = run_cost_scenarios(integrity, report, simulation, accounting, calendar, partition)
        self.assertEqual([item.scenario_name for item in results], [
            "baseline", "spread_stress", "slippage_stress", "commission_stress", "combined_adverse",
        ])
        self.assertEqual(len({item.simulation_id for item in results}), 5)
        self.assertLessEqual(results[-1].net_pnl, results[0].net_pnl)
        # Zero baseline commission remains zero under 2x, rather than inventing a fee.
        self.assertEqual(results[3].net_pnl, results[0].net_pnl)

    def test_boundary_signal_observable_at_end_never_creates_partition_trade(self) -> None:
        integrity, report, simulation, calendar = build_context(signals=(setup(2),), holding=1)
        partition = ChronologicalPartition(
            PartitionName.VALIDATION, START, START + timedelta(hours=3),
            0, 3, 3, "p" * 64,
        )
        accounting = AccountingConfig("USD", Decimal("10000"), "USD", True, timedelta(hours=24))
        baseline = run_cost_scenarios(
            integrity, report, simulation, accounting, calendar, partition,
            scenarios=(approved_cost_scenarios()[0],),
        )[0]
        self.assertEqual(baseline.trade_count, 0)


if __name__ == "__main__": unittest.main()
