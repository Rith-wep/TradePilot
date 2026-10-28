"""Typed contracts for TradePilot instruments and canonical bid/ask candles."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class Instrument:
    """Metadata needed to interpret FX prices without provider assumptions."""

    symbol: str
    base_currency: str
    quote_currency: str
    pip_size: Decimal
    price_precision: int

    def __post_init__(self) -> None:
        if len(self.symbol) != 6 or not self.symbol.isalpha() or not self.symbol.isupper():
            raise ValueError("symbol must be a six-letter uppercase FX symbol")
        for name, value in (
            ("base_currency", self.base_currency),
            ("quote_currency", self.quote_currency),
        ):
            if len(value) != 3 or not value.isalpha() or not value.isupper():
                raise ValueError(f"{name} must be a three-letter uppercase currency code")
        if self.symbol != self.base_currency + self.quote_currency:
            raise ValueError("symbol must equal base_currency + quote_currency")
        if self.pip_size <= 0:
            raise ValueError("pip_size must be positive")
        if self.price_precision < 0:
            raise ValueError("price_precision must not be negative")


@dataclass(frozen=True, slots=True)
class Candle:
    """Canonical H1 candle; timestamp is the UTC candle-open time."""

    instrument: Instrument
    timestamp: datetime
    timeframe: str
    bid_open: Decimal
    bid_high: Decimal
    bid_low: Decimal
    bid_close: Decimal
    ask_open: Decimal
    ask_high: Decimal
    ask_low: Decimal
    ask_close: Decimal
    source: str
    dataset_version: str
    is_synthetic: bool

