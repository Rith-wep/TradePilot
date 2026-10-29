"""Fold dispersion and explicit baseline-to-stress degradation summaries."""

from decimal import Decimal
from typing import Sequence

from tradepilot.accounting.models import MetricStatus, MetricValue
from tradepilot.validation.models import ConfigurationEvaluation, RobustnessSummary, StressDegradation


def summarize_robustness(evaluations: Sequence[ConfigurationEvaluation]) -> RobustnessSummary:
    values = []
    zero = 0
    insufficient = 0
    for evaluation in evaluations:
        baseline = next((item for item in evaluation.scenarios if item.scenario_name == "baseline"), None)
        if baseline is None or baseline.expectancy.value is None:
            insufficient += 1
            continue
        if baseline.trade_count == 0:
            zero += 1
        values.append(baseline.expectancy.value)
    positive = sum(value > 0 for value in values)
    fold_count = len(evaluations)
    fraction = (
        MetricValue(Decimal(positive) / Decimal(fold_count), MetricStatus.DEFINED)
        if fold_count else MetricValue(None, MetricStatus.UNDEFINED_NO_TRADES)
    )
    ordered = sorted(values)
    if ordered:
        middle = len(ordered) // 2
        median = ordered[middle] if len(ordered) % 2 else (ordered[middle - 1] + ordered[middle]) / Decimal(2)
        median_value = MetricValue(median, MetricStatus.DEFINED)
        range_value = MetricValue(ordered[-1] - ordered[0], MetricStatus.DEFINED)
    else:
        median_value = MetricValue(None, MetricStatus.UNDEFINED_NO_TRADES)
        range_value = MetricValue(None, MetricStatus.UNDEFINED_NO_TRADES)
    degradation = _stress_degradation(evaluations[-1]) if evaluations else ()
    return RobustnessSummary(
        fold_count, positive, zero, insufficient, fraction,
        median_value, range_value, degradation,
    )


def _stress_degradation(evaluation: ConfigurationEvaluation) -> tuple[StressDegradation, ...]:
    baseline = next((item for item in evaluation.scenarios if item.scenario_name == "baseline"), None)
    if baseline is None or baseline.expectancy.value is None:
        return ()
    output = []
    for scenario in evaluation.scenarios:
        if scenario.scenario_name == "baseline":
            continue
        if scenario.expectancy.value is None:
            undefined = MetricValue(None, scenario.expectancy.status)
            output.append(StressDegradation(scenario.scenario_name, undefined, undefined))
            continue
        change = scenario.expectancy.value - baseline.expectancy.value
        absolute = MetricValue(change, MetricStatus.DEFINED)
        relative = (
            MetricValue(change / abs(baseline.expectancy.value), MetricStatus.DEFINED)
            if baseline.expectancy.value != 0
            else MetricValue(None, MetricStatus.UNDEFINED_NO_TRADES)
        )
        output.append(StressDegradation(scenario.scenario_name, absolute, relative))
    return tuple(output)
