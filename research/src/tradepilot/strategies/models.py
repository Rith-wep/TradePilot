"""Immutable strategy inputs and candidate-setup records."""

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum

from tradepilot.indicators.models import IndicatorSeries


class Direction(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"


def _json_value(value: Decimal | str | int | bool | None) -> str | int | bool | None:
    return format(value, "f") if isinstance(value, Decimal) else value


@dataclass(frozen=True, slots=True)
class NamedValue:
    name: str
    value: Decimal | str | int | bool | None

    def to_dict(self) -> dict[str, object]:
        return {"name": self.name, "value": _json_value(self.value)}


@dataclass(frozen=True, slots=True)
class RuleEvidence:
    rule: str
    passed: bool
    actual: Decimal | str | int | bool | None
    expected: str

    def to_dict(self) -> dict[str, object]:
        return {
            "rule": self.rule,
            "passed": self.passed,
            "actual": _json_value(self.actual),
            "expected": self.expected,
        }


@dataclass(frozen=True, slots=True)
class StrategyIndicators:
    ema: IndicatorSeries | None = None
    rsi: IndicatorSeries | None = None
    atr: IndicatorSeries | None = None


@dataclass(frozen=True, slots=True)
class SetupRecord:
    strategy_name: str
    strategy_version: str
    instrument: str
    timeframe: str
    detection_candle_open_time: datetime
    observable_at: datetime
    direction: Direction
    setup_type: str
    indicator_values: tuple[NamedValue, ...]
    rule_evidence: tuple[RuleEvidence, ...]
    invalidation_conditions: tuple[str, ...]
    structural_invalidation_reference: Decimal | None
    configuration_fingerprint: str

    @property
    def identity_key(self) -> tuple[str, str, str, str, Direction, datetime]:
        return (
            self.strategy_name,
            self.strategy_version,
            self.instrument,
            self.timeframe,
            self.direction,
            self.detection_candle_open_time,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "strategy_name": self.strategy_name,
            "strategy_version": self.strategy_version,
            "instrument": self.instrument,
            "timeframe": self.timeframe,
            "detection_candle_open_time": self.detection_candle_open_time.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            "observable_at": self.observable_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            "direction": self.direction.value,
            "setup_type": self.setup_type,
            "indicator_values": [item.to_dict() for item in self.indicator_values],
            "rule_evidence": [item.to_dict() for item in self.rule_evidence],
            "invalidation_conditions": list(self.invalidation_conditions),
            "structural_invalidation_reference": (
                format(self.structural_invalidation_reference, "f")
                if self.structural_invalidation_reference is not None else None
            ),
            "configuration_fingerprint": self.configuration_fingerprint,
        }


def deduplicate_setups(setups: tuple[SetupRecord, ...] | list[SetupRecord]) -> tuple[SetupRecord, ...]:
    unique: dict[tuple[str, str, str, str, Direction, datetime], SetupRecord] = {}
    for setup in setups:
        prior = unique.get(setup.identity_key)
        if prior is not None and prior != setup:
            raise ValueError(f"conflicting duplicate setup: {setup.identity_key}")
        unique[setup.identity_key] = setup
    return tuple(unique[key] for key in sorted(unique, key=lambda item: (item[-1], item[-2].value)))

