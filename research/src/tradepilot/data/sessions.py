"""Configurable market-session calendars and missing-interval classification."""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Literal, Protocol, Sequence
from zoneinfo import ZoneInfo

from tradepilot.data.models import Candle


GapKind = Literal["expected_closure", "unexpected_missing"]


class TradingSessionCalendar(Protocol):
    @property
    def calendar_id(self) -> str: ...

    def is_expected_open(self, timestamp: datetime) -> bool: ...


@dataclass(frozen=True, slots=True)
class WeeklySessionCalendar:
    """A configurable weekly session plus optional full local-date closures.

    Weekdays use Monday=0 through Sunday=6. The default models a common FX
    week, not a universal broker schedule. Evaluation in ``timezone_name``
    supports broker-local schedules and daylight-saving changes.
    """

    timezone_name: str = "UTC"
    open_weekday: int = 6
    open_time: time = time(22, 0)
    close_weekday: int = 4
    close_time: time = time(22, 0)
    closure_dates: frozenset[date] = frozenset()
    name: str = "fx-weekly-default"

    def __post_init__(self) -> None:
        if not 0 <= self.open_weekday <= 6 or not 0 <= self.close_weekday <= 6:
            raise ValueError("session weekdays must be between 0 and 6")
        ZoneInfo(self.timezone_name)

    @property
    def calendar_id(self) -> str:
        closures = ",".join(sorted(day.isoformat() for day in self.closure_dates))
        return (
            f"{self.name}:{self.timezone_name}:"
            f"{self.open_weekday}-{self.open_time.isoformat()}:"
            f"{self.close_weekday}-{self.close_time.isoformat()}:"
            f"closures={closures}"
        )

    @staticmethod
    def _week_position(weekday: int, value: time) -> int:
        return weekday * 86_400 + value.hour * 3_600 + value.minute * 60 + value.second

    def is_expected_open(self, timestamp: datetime) -> bool:
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValueError("session timestamp must be timezone-aware")
        local = timestamp.astimezone(ZoneInfo(self.timezone_name))
        if local.date() in self.closure_dates:
            return False
        position = self._week_position(local.weekday(), local.timetz().replace(tzinfo=None))
        opened = self._week_position(self.open_weekday, self.open_time)
        closed = self._week_position(self.close_weekday, self.close_time)
        if opened < closed:
            return opened <= position < closed
        return position >= opened or position < closed


@dataclass(frozen=True, slots=True)
class MissingInterval:
    timestamp: datetime
    classification: GapKind

    def to_dict(self) -> dict[str, str]:
        return {
            "timestamp": self.timestamp.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            "classification": self.classification,
        }


@dataclass(frozen=True, slots=True)
class GapReport:
    calendar_id: str
    expected_closure_count: int
    unexpected_missing_count: int
    intervals: tuple[MissingInterval, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "calendar_id": self.calendar_id,
            "expected_closure_count": self.expected_closure_count,
            "unexpected_missing_count": self.unexpected_missing_count,
            "intervals": [interval.to_dict() for interval in self.intervals],
        }


def classify_gaps(
    candles: Sequence[Candle],
    calendar: TradingSessionCalendar,
    *,
    interval: timedelta = timedelta(hours=1),
) -> GapReport:
    """Classify absent timestamps between candles without modifying the data."""

    if interval <= timedelta(0):
        raise ValueError("interval must be positive")
    intervals: list[MissingInterval] = []
    ordered = sorted(candles, key=lambda candle: candle.timestamp)
    for previous, current in zip(ordered, ordered[1:]):
        missing = previous.timestamp + interval
        while missing < current.timestamp:
            classification: GapKind = (
                "unexpected_missing" if calendar.is_expected_open(missing) else "expected_closure"
            )
            intervals.append(MissingInterval(missing, classification))
            missing += interval
    return GapReport(
        calendar_id=calendar.calendar_id,
        expected_closure_count=sum(item.classification == "expected_closure" for item in intervals),
        unexpected_missing_count=sum(item.classification == "unexpected_missing" for item in intervals),
        intervals=tuple(intervals),
    )

