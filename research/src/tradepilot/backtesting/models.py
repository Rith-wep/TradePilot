"""Shared immutable value objects for provider-neutral forex backtesting."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum


def require_utc(name: str, value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError(f"{name} must be explicitly UTC")


def require_positive_decimal(name: str, value: Decimal) -> None:
    if not isinstance(value, Decimal) or not value.is_finite() or value <= 0:
        raise ValueError(f"{name} must be a positive finite Decimal")


def require_nonnegative_decimal(name: str, value: Decimal) -> None:
    if not isinstance(value, Decimal) or not value.is_finite() or value < 0:
        raise ValueError(f"{name} must be a non-negative finite Decimal")


def require_currency(name: str, value: str) -> None:
    if len(value) != 3 or not value.isalpha() or not value.isupper():
        raise ValueError(f"{name} must be a three-letter uppercase currency code")


def require_sha256(name: str, value: str) -> None:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError(f"{name} must be a lowercase SHA-256 value")


class TradeDirection(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"


@dataclass(frozen=True, slots=True)
class InstrumentSpec:
    symbol: str
    base_currency: str
    quote_currency: str
    pip_size: Decimal
    price_precision: int
    quantity_increment: Decimal

    def __post_init__(self) -> None:
        require_currency("base_currency", self.base_currency)
        require_currency("quote_currency", self.quote_currency)
        if self.symbol != self.base_currency + self.quote_currency:
            raise ValueError("symbol must equal base_currency + quote_currency")
        require_positive_decimal("pip_size", self.pip_size)
        require_positive_decimal("quantity_increment", self.quantity_increment)
        if isinstance(self.price_precision, bool) or not isinstance(self.price_precision, int) or self.price_precision < 0:
            raise ValueError("price_precision must be a non-negative integer")
        quantum = Decimal(1).scaleb(-self.price_precision)
        if self.pip_size != self.pip_size.quantize(quantum):
            raise ValueError("pip_size cannot exceed instrument price precision")


@dataclass(frozen=True, slots=True)
class BacktestProvenance:
    dataset_id: str
    dataset_checksum: str
    research_report_id: str
    strategy_name: str
    strategy_version: str
    configuration_fingerprint: str
    implementation_revision: str

    def __post_init__(self) -> None:
        for name in ("dataset_id", "dataset_checksum", "research_report_id", "configuration_fingerprint"):
            require_sha256(name, getattr(self, name))
        for name in ("strategy_name", "strategy_version", "implementation_revision"):
            if not getattr(self, name).strip():
                raise ValueError(f"{name} must not be empty")


@dataclass(frozen=True, slots=True)
class CurrencyConversionObservation:
    base_currency: str
    quote_currency: str
    rate: Decimal
    observed_at: datetime
    source: str
    dataset_id: str
    dataset_checksum: str

    def __post_init__(self) -> None:
        require_currency("base_currency", self.base_currency)
        require_currency("quote_currency", self.quote_currency)
        if self.base_currency == self.quote_currency:
            raise ValueError("conversion currencies must differ")
        require_positive_decimal("rate", self.rate)
        require_utc("observed_at", self.observed_at)
        if not self.source.strip():
            raise ValueError("conversion source must not be empty")
        for name in ("dataset_id", "dataset_checksum"):
            require_sha256(name, getattr(self, name))
