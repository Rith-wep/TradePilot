"""Credential-gated provider connectivity probes with no synthetic fallback."""

from dataclasses import dataclass
from datetime import datetime

from tradepilot.data.models import Instrument
from tradepilot.data.providers.base import MarketDataProvider, ProviderError, ProviderRequest


@dataclass(frozen=True, slots=True)
class ConnectivityResult:
    connected: bool
    provider: str
    instrument: str
    candle_count: int
    error_code: str | None


def verify_connectivity(
    provider: MarketDataProvider, instrument: Instrument, start: datetime, end: datetime,
    *, timeout_seconds: float = 30.0,
) -> ConnectivityResult:
    try:
        page = provider.fetch_page(ProviderRequest(instrument, "H1", start, end, timeout_seconds))
    except TimeoutError:
        return ConnectivityResult(False, provider.name, instrument.symbol, 0, "TIMEOUT")
    except ProviderError:
        return ConnectivityResult(False, provider.name, instrument.symbol, 0, "PROVIDER_REJECTED")
    candles = tuple(page.candles)
    if not candles or any(not item.complete for item in candles):
        return ConnectivityResult(False, provider.name, instrument.symbol, len(candles), "NO_COMPLETED_CANDLES")
    return ConnectivityResult(True, provider.name, instrument.symbol, len(candles), None)
