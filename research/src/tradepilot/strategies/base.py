"""Common strategy protocol, fingerprinting, and validation helpers."""

import hashlib
import json
from dataclasses import asdict, is_dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Protocol, Sequence

from tradepilot.data.models import Candle
from tradepilot.data.sessions import TradingSessionCalendar, classify_gaps
from tradepilot.data.validation import validate_candles
from tradepilot.indicators.models import IndicatorSeries, PriceBasis
from tradepilot.strategies.models import SetupRecord, StrategyIndicators


class StrategyInputError(ValueError):
    """Raised for invalid candles, configuration, gaps, or indicator alignment."""


class TradingStrategy(Protocol):
    name: str
    version: str

    def detect(
        self,
        candles: Sequence[Candle],
        indicators: StrategyIndicators,
        calendar: TradingSessionCalendar,
    ) -> tuple[SetupRecord, ...]: ...


def _json_default(value: object) -> object:
    if isinstance(value, Decimal):
        return format(value, "f")
    if is_dataclass(value):
        return asdict(value)
    raise TypeError(f"unsupported fingerprint value: {type(value).__name__}")


def configuration_fingerprint(
    strategy_name: str,
    strategy_version: str,
    configuration: object,
    calendar_id: str,
) -> str:
    payload = {
        "strategy_name": strategy_name,
        "strategy_version": strategy_version,
        "configuration": configuration,
        "calendar_id": calendar_id,
    }
    encoded = json.dumps(payload, default=_json_default, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def validate_strategy_candles(
    candles: Sequence[Candle],
    calendar: TradingSessionCalendar,
    *,
    reject_unexpected_gaps: bool,
) -> tuple[Candle, ...]:
    values = tuple(candles)
    if not values:
        return values
    report = validate_candles(values)
    if not report.valid:
        codes = ", ".join(issue.code for issue in report.issues if issue.severity == "error")
        raise StrategyInputError(f"candles failed canonical validation: {codes}")
    first = values[0]
    if any(candle.instrument != first.instrument for candle in values):
        raise StrategyInputError("all candles must use the same instrument metadata")
    if any(candle.timeframe != first.timeframe for candle in values):
        raise StrategyInputError("all candles must use the same timeframe")
    if first.timeframe != "H1":
        raise StrategyInputError("only H1 observability is currently defined")
    gaps = classify_gaps(values, calendar)
    if reject_unexpected_gaps and gaps.unexpected_missing_count:
        raise StrategyInputError(
            f"dataset contains {gaps.unexpected_missing_count} unexpected missing H1 intervals"
        )
    return values


def validate_indicator_alignment(
    candles: Sequence[Candle],
    series: IndicatorSeries,
    *,
    name: str,
    period: int,
    price_basis: PriceBasis,
) -> None:
    if series.name != name or series.period != period or series.price_basis != price_basis:
        raise StrategyInputError(
            f"{name} series metadata does not match strategy configuration"
        )
    if len(series.points) != len(candles):
        raise StrategyInputError(f"{name} series length does not match candles")
    if any(point.timestamp != candle.timestamp for point, candle in zip(series.points, candles, strict=True)):
        raise StrategyInputError(f"{name} timestamps do not align with candles")


def candle_price(candle: Candle, field: str, price_basis: PriceBasis) -> Decimal:
    if price_basis == "bid":
        return getattr(candle, f"bid_{field}")
    if price_basis == "ask":
        return getattr(candle, f"ask_{field}")
    return (getattr(candle, f"bid_{field}") + getattr(candle, f"ask_{field}")) / Decimal(2)


def observable_time(candle: Candle) -> datetime:
    if candle.timeframe != "H1":
        raise StrategyInputError("only H1 observability is currently defined")
    return candle.timestamp + timedelta(hours=1)

