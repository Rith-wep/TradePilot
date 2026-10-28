"""Provider-neutral contracts for paginated historical candle retrieval."""

from dataclasses import dataclass
from datetime import datetime
from typing import Mapping, Protocol, Sequence, runtime_checkable

from tradepilot.data.models import Instrument


class ProviderError(RuntimeError):
    """A non-retryable market-data provider failure."""


class TransientProviderError(ProviderError):
    """A temporary provider failure that may be retried."""


class RateLimitError(TransientProviderError):
    """A provider rate limit; retry_after_seconds may guide backoff."""

    def __init__(self, message: str, retry_after_seconds: float | None = None) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


@dataclass(frozen=True, slots=True)
class ProviderRequest:
    instrument: Instrument
    timeframe: str
    start: datetime
    end: datetime
    timeout_seconds: float = 30.0


@dataclass(frozen=True, slots=True)
class ProviderCandle:
    """Untrusted provider candle; timestamp must denote the candle open."""

    timestamp: datetime
    timeframe: str
    bid_open: str
    bid_high: str
    bid_low: str
    bid_close: str
    ask_open: str
    ask_high: str
    ask_low: str
    ask_close: str
    complete: bool = True


@dataclass(frozen=True, slots=True)
class ProviderPage:
    candles: Sequence[ProviderCandle]
    next_cursor: str | None = None
    metadata: Mapping[str, str] | None = None


@runtime_checkable
class MarketDataProvider(Protocol):
    """Interface implemented by historical market-data adapters."""

    @property
    def name(self) -> str: ...

    @property
    def dataset_version(self) -> str: ...

    @property
    def is_synthetic(self) -> bool: ...

    def fetch_page(self, request: ProviderRequest, cursor: str | None = None) -> ProviderPage:
        """Return one page for the half-open interval [start, end)."""

