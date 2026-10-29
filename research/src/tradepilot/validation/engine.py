"""Small validation orchestration guards independent of strategy formulas."""

from collections.abc import Sequence

from tradepilot.validation.models import ConfigurationEvaluation, EvaluationStatus, ParameterDeclaration, ScenarioEvaluation


def configuration_evaluation(
    configuration: ParameterDeclaration,
    partition_id: str,
    scenarios: Sequence[ScenarioEvaluation],
    *,
    minimum_trades: int,
) -> ConfigurationEvaluation:
    """Classify a complete scenario set without discarding weak samples."""
    if minimum_trades < 0:
        raise ValueError("minimum_trades must not be negative")
    values = tuple(scenarios)
    warnings: list[str] = []
    if not values:
        status = EvaluationStatus.FAILED
        warnings.append("NO_SCENARIO_RESULTS")
    elif min(item.trade_count for item in values) == 0:
        status = EvaluationStatus.ZERO_TRADES
        warnings.append("ZERO_TRADES_RETAINED")
    elif min(item.trade_count for item in values) < minimum_trades:
        status = EvaluationStatus.INSUFFICIENT_TRADES
        warnings.append("INSUFFICIENT_TRADES_RETAINED")
    elif any(item.expectancy.value is None for item in values):
        status = EvaluationStatus.FAILED
        warnings.append("UNDEFINED_EXPECTANCY")
    else:
        status = EvaluationStatus.ELIGIBLE
    if any(item.forced_exits for item in values):
        warnings.append("FORCED_TERMINAL_EXITS_INCLUDED")
    if any(item.ambiguous_exits for item in values):
        warnings.append("AMBIGUOUS_EXITS_INCLUDED")
    return ConfigurationEvaluation(configuration, partition_id, values, status, tuple(warnings))
