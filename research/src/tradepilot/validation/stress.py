"""Cost scenarios that rerun execution and accounting from identical candidates."""

from dataclasses import dataclass, replace
from decimal import Decimal
from types import SimpleNamespace
from typing import Sequence

from tradepilot.accounting.engine import build_accounting
from tradepilot.accounting.models import AccountingConfig
from tradepilot.backtesting.models import CurrencyConversionObservation
from tradepilot.backtesting.policies import TransactionCostPolicy
from tradepilot.backtesting.simulation_models import SimulationCandidateReport, SimulationConfig
from tradepilot.backtesting.simulator import EventDrivenSimulator
from tradepilot.data.sessions import TradingSessionCalendar
from tradepilot.core.canonical import canonical_json_bytes, sha256_hex
from tradepilot.validation.models import ChronologicalPartition, ScenarioEvaluation
from tradepilot.validation.partitions import partition_candles
from tradepilot.validation.warmup import eligible_setups


@dataclass(frozen=True, slots=True)
class CostStressScenario:
    name: str
    additional_spread_increment_pips: Decimal
    slippage_increment_pips: Decimal
    commission_multiplier: Decimal

    @property
    def scenario_id(self) -> str:
        return sha256_hex(canonical_json_bytes(self))


def approved_cost_scenarios() -> tuple[CostStressScenario, ...]:
    return (
        CostStressScenario("baseline", Decimal(0), Decimal(0), Decimal(1)),
        CostStressScenario("spread_stress", Decimal(1), Decimal(0), Decimal(1)),
        CostStressScenario("slippage_stress", Decimal(0), Decimal(1), Decimal(1)),
        CostStressScenario("commission_stress", Decimal(0), Decimal(0), Decimal(2)),
        CostStressScenario("combined_adverse", Decimal(1), Decimal(1), Decimal(2)),
    )


def run_cost_scenarios(
    integrity,
    report: SimulationCandidateReport,
    simulation_config: SimulationConfig,
    accounting_config: AccountingConfig,
    calendar: TradingSessionCalendar,
    partition: ChronologicalPartition,
    observations: Sequence[CurrencyConversionObservation] = (),
    scenarios: Sequence[CostStressScenario] | None = None,
) -> tuple[ScenarioEvaluation, ...]:
    sliced_candles = partition_candles(integrity.candles, partition)
    sliced_integrity = SimpleNamespace(
        valid=integrity.valid, candles=sliced_candles,
        dataset_id=integrity.dataset_id, dataset_checksum=integrity.dataset_checksum,
    )
    sliced_report = replace(report, signals=eligible_setups(report.signals, partition))
    output = []
    for scenario in scenarios or approved_cost_scenarios():
        execution = simulation_config.backtest.execution_policy
        stressed_execution = replace(
            execution,
            additional_spread_pips=execution.additional_spread_pips + scenario.additional_spread_increment_pips,
            slippage_pips=execution.slippage_pips + scenario.slippage_increment_pips,
        )
        cost = simulation_config.backtest.cost_policy
        stressed_cost = TransactionCostPolicy(
            f"{cost.version}:{scenario.name}", cost.commission_model,
            cost.commission_amount * scenario.commission_multiplier,
        )
        backtest = replace(
            simulation_config.backtest,
            execution_policy=stressed_execution,
            cost_policy=stressed_cost,
        )
        scenario_config = SimulationConfig(backtest, simulation_config.signal_order)
        simulation = EventDrivenSimulator().run(sliced_integrity, sliced_report, scenario_config, calendar)
        accounting = build_accounting(simulation, scenario_config, accounting_config, observations)
        metrics = accounting.content.metrics
        output.append(ScenarioEvaluation(
            scenario.scenario_id, scenario.name, simulation.simulation_id,
            accounting.report_id, metrics.closed_trades, metrics.expectancy,
            metrics.net_pnl, metrics.maximum_drawdown,
            metrics.forced_end_of_dataset_exits,
            metrics.ambiguous_intrabar_exits, metrics.unresolved_orders,
        ))
    return tuple(output)
