"""Approved bounded parameter declarations and deterministic selection."""

from dataclasses import asdict
from decimal import Decimal
from typing import Sequence

from tradepilot.reporting.canonical import canonical_json_bytes, sha256_hex
from tradepilot.strategies.base import configuration_fingerprint
from tradepilot.strategies.breakout import BreakoutConfig, PriceRangeBreakoutStrategy
from tradepilot.strategies.pullback import EmaRsiPullbackStrategy, PullbackConfig
from tradepilot.validation.models import (
    ConfigurationEvaluation, EvaluationStatus, ParameterDeclaration, SelectionDecision,
)


def approved_parameter_grid(calendar_id: str) -> tuple[tuple[object, ParameterDeclaration], ...]:
    values: list[tuple[object, ParameterDeclaration]] = []
    for config in (BreakoutConfig(lookback=10), BreakoutConfig(lookback=20), BreakoutConfig(lookback=40)):
        strategy = PriceRangeBreakoutStrategy(config)
        values.append((config, _declaration(strategy.name, strategy.version, config, calendar_id)))
    for config in (PullbackConfig(ema_period=100), PullbackConfig(ema_period=200)):
        strategy = EmaRsiPullbackStrategy(config)
        values.append((config, _declaration(strategy.name, strategy.version, config, calendar_id)))
    return tuple(values)


def _declaration(name: str, version: str, config: object, calendar_id: str) -> ParameterDeclaration:
    fingerprint = configuration_fingerprint(name, version, config, calendar_id)
    parameters = tuple(sorted(asdict(config).items()))
    return ParameterDeclaration(name, version, fingerprint, parameters)


def select_configuration(
    evaluations: Sequence[ConfigurationEvaluation],
    *,
    minimum_trades: int = 30,
    policy_id: str = "worst-stress-expectancy-drawdown-count-fingerprint/v1",
) -> SelectionDecision:
    if any(not isinstance(item, ConfigurationEvaluation) for item in evaluations):
        raise ValueError("selection accepts development evaluations only; locked-test metrics are forbidden")
    ranked = []
    rejected = []
    for evaluation in evaluations:
        fingerprint = evaluation.configuration.configuration_fingerprint
        if not evaluation.scenarios:
            rejected.append((fingerprint, "NO_SCENARIO_RESULTS"))
            continue
        minimum_count = min(item.trade_count for item in evaluation.scenarios)
        if minimum_count == 0:
            rejected.append((fingerprint, "ZERO_TRADES"))
            continue
        if minimum_count < minimum_trades:
            rejected.append((fingerprint, "INSUFFICIENT_TRADES"))
            continue
        if any(item.expectancy.value is None for item in evaluation.scenarios):
            rejected.append((fingerprint, "UNDEFINED_EXPECTANCY"))
            continue
        worst_expectancy = min(item.expectancy.value for item in evaluation.scenarios if item.expectancy.value is not None)
        worst_drawdown = max(item.maximum_drawdown for item in evaluation.scenarios)
        ranked.append((worst_expectancy, -worst_drawdown, minimum_count, fingerprint))
    ranked.sort(key=lambda item: (-item[0], -item[1], -item[2], item[3]))
    selected = ranked[0][3] if ranked else None
    eligible = tuple(item[3] for item in ranked)
    identity = sha256_hex(canonical_json_bytes({
        "policy_id": policy_id, "minimum_trades": minimum_trades,
        "eligible": eligible, "rejected": tuple(sorted(rejected)), "selected": selected,
    }))
    return SelectionDecision(policy_id, selected, eligible, tuple(sorted(rejected)), identity)
