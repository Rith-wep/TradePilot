"""Pure Decimal implementations of EMA, Wilder RSI, and Wilder ATR."""

from decimal import Decimal, localcontext
from typing import Sequence

from tradepilot.data.models import Candle
from tradepilot.data.validation import validate_candles
from tradepilot.indicators.models import IndicatorPoint, IndicatorSeries, PriceBasis


DECIMAL_PRECISION = 34


class IndicatorInputError(ValueError):
    """Raised when indicator parameters or canonical candles are invalid."""


def _validate_period(period: int) -> None:
    if isinstance(period, bool) or not isinstance(period, int) or period <= 0:
        raise IndicatorInputError("period must be a positive integer")


def _validate_basis(price_basis: PriceBasis) -> None:
    if price_basis not in ("bid", "ask", "mid"):
        raise IndicatorInputError("price_basis must be 'bid', 'ask', or 'mid'")


def _validated_candles(candles: Sequence[Candle]) -> tuple[Candle, ...]:
    if candles is None:  # type: ignore[comparison-overlap]
        raise TypeError("candles must be a sequence, not None")
    try:
        values = tuple(candles)
    except TypeError as exc:
        raise TypeError("candles must be a sequence") from exc
    if not values:
        return values
    first = values[0]
    if any(candle.instrument != first.instrument for candle in values):
        raise IndicatorInputError("all candles must use the same instrument metadata")
    if any(candle.timeframe != first.timeframe for candle in values):
        raise IndicatorInputError("all candles must use the same timeframe")
    for candle in values:
        prices = (
            candle.bid_open, candle.bid_high, candle.bid_low, candle.bid_close,
            candle.ask_open, candle.ask_high, candle.ask_low, candle.ask_close,
        )
        if any(not isinstance(price, Decimal) or not price.is_finite() for price in prices):
            raise IndicatorInputError("all candle prices must be finite Decimal values")
    try:
        report = validate_candles(values)
    except (ArithmeticError, TypeError, ValueError) as exc:
        raise IndicatorInputError(f"candles cannot be validated: {exc}") from exc
    if not report.valid:
        codes = ", ".join(issue.code for issue in report.issues if issue.severity == "error")
        raise IndicatorInputError(f"candles failed canonical validation: {codes}")
    return values


def _price(candle: Candle, field: str, price_basis: PriceBasis) -> Decimal:
    if price_basis == "bid":
        return getattr(candle, f"bid_{field}")
    if price_basis == "ask":
        return getattr(candle, f"ask_{field}")
    return (getattr(candle, f"bid_{field}") + getattr(candle, f"ask_{field}")) / Decimal(2)


def _points(candles: Sequence[Candle], values: Sequence[Decimal | None]) -> tuple[IndicatorPoint, ...]:
    return tuple(IndicatorPoint(candle.timestamp, value) for candle, value in zip(candles, values, strict=True))


def ema(candles: Sequence[Candle], period: int, price_basis: PriceBasis = "mid") -> IndicatorSeries:
    """EMA of selected close prices, seeded with an initial simple average."""

    _validate_period(period)
    _validate_basis(price_basis)
    values = _validated_candles(candles)
    output: list[Decimal | None] = [None] * len(values)
    if len(values) < period:
        return IndicatorSeries("EMA", period, price_basis, _points(values, output))
    with localcontext() as context:
        context.prec = DECIMAL_PRECISION
        closes = [_price(candle, "close", price_basis) for candle in values]
        current = sum(closes[:period], Decimal(0)) / Decimal(period)
        output[period - 1] = current
        alpha = Decimal(2) / Decimal(period + 1)
        for index in range(period, len(closes)):
            current = alpha * closes[index] + (Decimal(1) - alpha) * current
            output[index] = current
    return IndicatorSeries("EMA", period, price_basis, _points(values, output))


def _rsi_value(average_gain: Decimal, average_loss: Decimal) -> Decimal:
    if average_gain == 0 and average_loss == 0:
        return Decimal(50)
    if average_loss == 0:
        return Decimal(100)
    relative_strength = average_gain / average_loss
    return Decimal(100) - Decimal(100) / (Decimal(1) + relative_strength)


def rsi(candles: Sequence[Candle], period: int, price_basis: PriceBasis = "mid") -> IndicatorSeries:
    """RSI using Wilder's initial averages and recursive smoothing."""

    _validate_period(period)
    _validate_basis(price_basis)
    values = _validated_candles(candles)
    output: list[Decimal | None] = [None] * len(values)
    if len(values) <= period:
        return IndicatorSeries("RSI", period, price_basis, _points(values, output))
    with localcontext() as context:
        context.prec = DECIMAL_PRECISION
        closes = [_price(candle, "close", price_basis) for candle in values]
        changes = [current - previous for previous, current in zip(closes, closes[1:])]
        gains = [max(change, Decimal(0)) for change in changes]
        losses = [max(-change, Decimal(0)) for change in changes]
        average_gain = sum(gains[:period], Decimal(0)) / Decimal(period)
        average_loss = sum(losses[:period], Decimal(0)) / Decimal(period)
        output[period] = _rsi_value(average_gain, average_loss)
        for index in range(period, len(changes)):
            average_gain = (average_gain * Decimal(period - 1) + gains[index]) / Decimal(period)
            average_loss = (average_loss * Decimal(period - 1) + losses[index]) / Decimal(period)
            output[index + 1] = _rsi_value(average_gain, average_loss)
    return IndicatorSeries("RSI", period, price_basis, _points(values, output))


def atr(candles: Sequence[Candle], period: int, price_basis: PriceBasis = "mid") -> IndicatorSeries:
    """ATR using true ranges and Wilder's recursive smoothing."""

    _validate_period(period)
    _validate_basis(price_basis)
    values = _validated_candles(candles)
    output: list[Decimal | None] = [None] * len(values)
    if len(values) < period:
        return IndicatorSeries("ATR", period, price_basis, _points(values, output))
    with localcontext() as context:
        context.prec = DECIMAL_PRECISION
        true_ranges: list[Decimal] = []
        previous_close: Decimal | None = None
        for candle in values:
            high = _price(candle, "high", price_basis)
            low = _price(candle, "low", price_basis)
            if previous_close is None:
                true_range = high - low
            else:
                true_range = max(high - low, abs(high - previous_close), abs(low - previous_close))
            true_ranges.append(true_range)
            previous_close = _price(candle, "close", price_basis)
        current = sum(true_ranges[:period], Decimal(0)) / Decimal(period)
        output[period - 1] = current
        for index in range(period, len(true_ranges)):
            current = (current * Decimal(period - 1) + true_ranges[index]) / Decimal(period)
            output[index] = current
    return IndicatorSeries("ATR", period, price_basis, _points(values, output))

