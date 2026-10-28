"""Typed immutable outputs for technical indicator calculations."""

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal


PriceBasis = Literal["bid", "ask", "mid"]


@dataclass(frozen=True, slots=True)
class IndicatorPoint:
    timestamp: datetime
    value: Decimal | None

    def to_dict(self) -> dict[str, str | None]:
        return {
            "timestamp": self.timestamp.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            "value": format(self.value, "f") if self.value is not None else None,
        }


@dataclass(frozen=True, slots=True)
class IndicatorSeries:
    name: Literal["EMA", "RSI", "ATR"]
    period: int
    price_basis: PriceBasis
    points: tuple[IndicatorPoint, ...]

    @property
    def warmup_count(self) -> int:
        return sum(point.value is None for point in self.points)

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "period": self.period,
            "price_basis": self.price_basis,
            "warmup_count": self.warmup_count,
            "points": [point.to_dict() for point in self.points],
        }

