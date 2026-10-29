"""Deterministic validation and quality reporting for canonical candles."""

from dataclasses import asdict, dataclass
from datetime import timedelta, timezone
from decimal import Decimal
from typing import Literal, Sequence

from tradepilot.data.models import Candle


@dataclass(frozen=True, slots=True)
class QualityIssue:
    severity: Literal["error", "warning"]
    code: str
    message: str
    row: int | None = None


@dataclass(frozen=True, slots=True)
class QualityReport:
    candle_count: int
    error_count: int
    warning_count: int
    valid: bool
    first_timestamp: str | None
    last_timestamp: str | None
    issues: tuple[QualityIssue, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "candle_count": self.candle_count,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "valid": self.valid,
            "first_timestamp": self.first_timestamp,
            "last_timestamp": self.last_timestamp,
            "issues": [asdict(issue) for issue in self.issues],
        }


def _ohlc_issue(prefix: str, open_: Decimal, high: Decimal, low: Decimal, close: Decimal) -> str | None:
    if any(price <= 0 for price in (open_, high, low, close)):
        return f"{prefix} prices must all be positive"
    if low > high:
        return f"{prefix} low must not exceed high"
    if not low <= open_ <= high or not low <= close <= high:
        return f"{prefix} open and close must be within low/high"
    return None


def validate_candles(
    candles: Sequence[Candle], *, unusual_spread_pips: Decimal = Decimal("20")
) -> QualityReport:
    """Validate file order and each H1 bid/ask candle without changing data."""

    if unusual_spread_pips <= 0:
        raise ValueError("unusual_spread_pips must be positive")

    issues: list[QualityIssue] = []
    seen_timestamps: set[object] = set()

    for index, candle in enumerate(candles, start=1):
        timestamp = candle.timestamp
        if timestamp.tzinfo is None or timestamp.utcoffset() != timedelta(0):
            issues.append(QualityIssue("error", "timestamp_not_utc", "timestamp must be UTC-aware", index))
        if timestamp.minute or timestamp.second or timestamp.microsecond:
            issues.append(QualityIssue("error", "timestamp_not_hour_aligned", "H1 timestamp must start on the hour", index))
        if candle.timeframe != "H1":
            issues.append(QualityIssue("error", "unsupported_timeframe", "timeframe must be H1", index))
        if timestamp in seen_timestamps:
            issues.append(QualityIssue("error", "duplicate_timestamp", "duplicate candle timestamp", index))
        seen_timestamps.add(timestamp)
        if index > 1:
            previous = candles[index - 2].timestamp
            if timestamp < previous:
                issues.append(QualityIssue("error", "out_of_order", "timestamps must be chronological", index))
            elif timestamp - previous > timedelta(hours=1):
                issues.append(QualityIssue("warning", "time_gap", "gap exceeds one H1 interval; data was not filled", index))

        for prefix, prices in (
            ("bid", (candle.bid_open, candle.bid_high, candle.bid_low, candle.bid_close)),
            ("ask", (candle.ask_open, candle.ask_high, candle.ask_low, candle.ask_close)),
        ):
            message = _ohlc_issue(prefix, *prices)
            if message:
                issues.append(QualityIssue("error", f"invalid_{prefix}_ohlc", message, index))

        if any(bid > ask for bid, ask in zip(
            (candle.bid_open, candle.bid_high, candle.bid_low, candle.bid_close),
            (candle.ask_open, candle.ask_high, candle.ask_low, candle.ask_close),
        )):
            issues.append(QualityIssue("error", "bid_above_ask", "bid must not exceed ask for corresponding OHLC fields", index))
        spreads = tuple(ask - bid for bid, ask in zip(
            (candle.bid_open, candle.bid_high, candle.bid_low, candle.bid_close),
            (candle.ask_open, candle.ask_high, candle.ask_low, candle.ask_close),
        ))
        threshold = candle.instrument.pip_size * unusual_spread_pips
        if spreads and max(spreads) > threshold:
            issues.append(QualityIssue(
                "warning", "unusual_spread",
                f"bid/ask spread exceeds {format(unusual_spread_pips, 'f')} pips; candle retained",
                index,
            ))
        if not candle.source.strip() or not candle.dataset_version.strip():
            issues.append(QualityIssue("error", "missing_provenance", "source and dataset_version are required", index))

    errors = sum(issue.severity == "error" for issue in issues)
    warnings = sum(issue.severity == "warning" for issue in issues)
    utc_timestamps = [
        candle.timestamp.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        for candle in candles
        if candle.timestamp.tzinfo is not None
    ]
    return QualityReport(
        candle_count=len(candles),
        error_count=errors,
        warning_count=warnings,
        valid=errors == 0,
        first_timestamp=utc_timestamps[0] if utc_timestamps else None,
        last_timestamp=utc_timestamps[-1] if utc_timestamps else None,
        issues=tuple(issues),
    )

