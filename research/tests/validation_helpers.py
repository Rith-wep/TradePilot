from datetime import timedelta
from decimal import Decimal

from simulator_helpers import HASH_A, START, candle, setup
from tradepilot.accounting.models import MetricStatus, MetricValue
from tradepilot.validation.models import (
    ConfigurationEvaluation, EvaluationStatus, ParameterDeclaration, ScenarioEvaluation,
)


def candles(count=100):
    return tuple(candle(index) for index in range(count))


def declaration(fingerprint="a" * 64):
    return ParameterDeclaration("strategy", "1.0.0", fingerprint, (("period", 20),))


def scenario(name="baseline", expectancy="1", trades=30, suffix="a"):
    return ScenarioEvaluation(
        suffix * 64, name, (suffix.upper() if suffix.isalpha() else "b") * 64,
        "c" * 64, trades,
        MetricValue(Decimal(expectancy), MetricStatus.DEFINED) if expectancy is not None else MetricValue(None, MetricStatus.UNDEFINED_NO_TRADES),
        Decimal(expectancy or 0) * Decimal(trades), Decimal("2"), 0, 0, 0,
    )


def evaluation(fingerprint="a" * 64, expectancy="1", trades=30):
    return ConfigurationEvaluation(
        declaration(fingerprint), "p" * 64,
        (scenario(expectancy=expectancy, trades=trades),), EvaluationStatus.ELIGIBLE,
    )
