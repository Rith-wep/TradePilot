"""Normalize untrusted provider records into canonical TradePilot candles."""

from datetime import timedelta, timezone
from decimal import Decimal, InvalidOperation

from tradepilot.data.models import Candle, Instrument
from tradepilot.data.providers.base import ProviderCandle


class NormalizationError(ValueError):
    """Raised when a provider record cannot become a canonical candle."""


def normalize_provider_candle(
    raw: ProviderCandle,
    *,
    instrument: Instrument,
    provider: str,
    dataset_version: str,
    is_synthetic: bool,
) -> Candle:
    """Normalize a complete candle whose timestamp represents its opening time."""

    if not raw.complete:
        raise NormalizationError("provider candle is incomplete")
    if raw.timestamp.tzinfo is None or raw.timestamp.utcoffset() is None:
        raise NormalizationError("provider timestamp must be timezone-aware")
    timestamp = raw.timestamp.astimezone(timezone.utc)
    if timestamp.utcoffset() != timedelta(0):  # defensive; astimezone guarantees this
        raise NormalizationError("provider timestamp could not be normalized to UTC")
    try:
        prices = {
            name: Decimal(getattr(raw, name))
            for name in (
                "bid_open", "bid_high", "bid_low", "bid_close",
                "ask_open", "ask_high", "ask_low", "ask_close",
            )
        }
    except (InvalidOperation, TypeError) as exc:
        raise NormalizationError(f"provider price is not a valid decimal: {exc}") from exc
    if any(not price.is_finite() for price in prices.values()):
        raise NormalizationError("provider prices must be finite decimals")
    return Candle(
        instrument=instrument,
        timestamp=timestamp,
        timeframe=raw.timeframe,
        **prices,
        source=provider,
        dataset_version=dataset_version,
        is_synthetic=is_synthetic,
    )

