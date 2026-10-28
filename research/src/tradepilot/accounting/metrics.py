"""Deterministic trade and equity metrics with explicit undefined states."""

from decimal import Decimal
from typing import Sequence

from tradepilot.accounting.models import (
    EquityPoint, MetricStatus, MetricValue, PerformanceMetrics, TradeAccounting,
)
from tradepilot.backtesting.simulation_models import AuditKind, SimulationResult


def _average(values: list[Decimal], undefined: MetricStatus) -> MetricValue:
    return MetricValue(sum(values, Decimal(0)) / Decimal(len(values)), MetricStatus.DEFINED) if values else MetricValue(None, undefined)


def calculate_metrics(
    trades: Sequence[TradeAccounting],
    equity: Sequence[EquityPoint],
    result: SimulationResult,
) -> PerformanceMetrics:
    outcomes = [item.net_pnl_account for item in trades]
    wins = [value for value in outcomes if value > 0]
    losses = [value for value in outcomes if value < 0]
    breakeven = [value for value in outcomes if value == 0]
    total = len(outcomes)
    net = sum(outcomes, Decimal(0))
    gross_profit = sum(wins, Decimal(0))
    gross_loss = -sum(losses, Decimal(0))
    if total:
        win_rate = MetricValue(Decimal(len(wins)) / Decimal(total), MetricStatus.DEFINED)
        expectancy = MetricValue(net / Decimal(total), MetricStatus.DEFINED)
    else:
        win_rate = MetricValue(None, MetricStatus.UNDEFINED_NO_TRADES)
        expectancy = MetricValue(None, MetricStatus.UNDEFINED_NO_TRADES)
    profit_factor = (
        MetricValue(gross_profit / gross_loss, MetricStatus.DEFINED)
        if gross_loss > 0 else MetricValue(None, MetricStatus.UNDEFINED_NO_LOSSES)
    )
    lowers = [
        Decimal((item.exit_timing.interval_start - item.entry_recognized_at).total_seconds())
        for item in trades
    ]
    uppers = [
        Decimal((item.exit_timing.interval_end - item.entry_recognized_at).total_seconds())
        for item in trades
    ]
    max_drawdown = max((item.drawdown_amount for item in equity), default=Decimal(0))
    defined_percentages = [
        item.drawdown_percentage.value for item in equity
        if item.drawdown_percentage.status is MetricStatus.DEFINED
    ]
    max_drawdown_percentage = (
        MetricValue(max(defined_percentages), MetricStatus.DEFINED)
        if defined_percentages else MetricValue(None, MetricStatus.UNDEFINED_NONPOSITIVE_PEAK)
    )
    unresolved = sum(event.kind is AuditKind.UNRESOLVED_END_OF_DATA for event in result.audit_log)
    return PerformanceMetrics(
        total, len(wins), len(losses), len(breakeven), win_rate,
        _average(wins, MetricStatus.UNDEFINED_NO_WINS),
        _average(losses, MetricStatus.UNDEFINED_NO_LOSSES),
        gross_profit, gross_loss, net, profit_factor, expectancy,
        max_drawdown, max_drawdown_percentage,
        _average(lowers, MetricStatus.UNDEFINED_NO_TRADES),
        _average(uppers, MetricStatus.UNDEFINED_NO_TRADES),
        unresolved,
        sum(item.forced_end_of_dataset for item in trades),
        sum(item.ambiguous_intrabar for item in trades),
    )
