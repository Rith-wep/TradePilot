from datetime import datetime, timedelta, timezone
from decimal import Decimal

from ingestion_helpers import EURUSD
from tradepilot.data.models import Candle
from tradepilot.indicators.models import IndicatorPoint, IndicatorSeries


START = datetime(2024, 1, 1, tzinfo=timezone.utc)


def strategy_candle(
    index: int,
    close: str,
    *,
    high: str | None = None,
    low: str | None = None,
    timestamp: datetime | None = None,
) -> Candle:
    close_value = Decimal(close)
    high_value = Decimal(high) if high is not None else close_value
    low_value = Decimal(low) if low is not None else close_value
    return Candle(
        instrument=EURUSD,
        timestamp=timestamp or START + timedelta(hours=index),
        timeframe="H1",
        bid_open=close_value,
        bid_high=high_value,
        bid_low=low_value,
        bid_close=close_value,
        ask_open=close_value,
        ask_high=high_value,
        ask_low=low_value,
        ask_close=close_value,
        source="strategy-test-synthetic",
        dataset_version="v1",
        is_synthetic=True,
    )


def indicator_series(name, period: int, candles: list[Candle], values, basis="mid") -> IndicatorSeries:
    return IndicatorSeries(
        name=name,
        period=period,
        price_basis=basis,
        points=tuple(
            IndicatorPoint(candle.timestamp, Decimal(str(value)) if value is not None else None)
            for candle, value in zip(candles, values, strict=True)
        ),
    )

