from datetime import datetime, timedelta, timezone
from decimal import Decimal

from tradepilot.data.models import Instrument
from tradepilot.data.providers.base import ProviderCandle


EURUSD = Instrument("EURUSD", "EUR", "USD", Decimal("0.0001"), 5)
START = datetime(2024, 1, 2, tzinfo=timezone.utc)


def raw_candle(index: int, **changes: object) -> ProviderCandle:
    base = Decimal("1.10000") + Decimal(index) * Decimal("0.00100")
    values: dict[str, object] = {
        "timestamp": START + timedelta(hours=index),
        "timeframe": "H1",
        "bid_open": str(base),
        "bid_high": str(base + Decimal("0.00080")),
        "bid_low": str(base - Decimal("0.00050")),
        "bid_close": str(base + Decimal("0.00030")),
        "ask_open": str(base + Decimal("0.00015")),
        "ask_high": str(base + Decimal("0.00095")),
        "ask_low": str(base - Decimal("0.00035")),
        "ask_close": str(base + Decimal("0.00045")),
        "complete": True,
    }
    values.update(changes)
    return ProviderCandle(**values)  # type: ignore[arg-type]

