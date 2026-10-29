"""Provider contracts and test adapters."""

from tradepilot.data.providers.base import (
    MarketDataProvider,
    ProviderCandle,
    ProviderError,
    ProviderPage,
    ProviderRequest,
    RateLimitError,
    TransientProviderError,
)
from tradepilot.data.providers.oanda import OandaMarketDataProvider, OandaProviderConfig
from tradepilot.data.providers.dukascopy_csv import DukascopyCsvMarketDataProvider, DukascopyCsvError

__all__ = [
    "MarketDataProvider",
    "ProviderCandle",
    "ProviderError",
    "ProviderPage",
    "ProviderRequest",
    "RateLimitError",
    "TransientProviderError",
    "OandaMarketDataProvider",
    "OandaProviderConfig",
    "DukascopyCsvMarketDataProvider",
    "DukascopyCsvError",
]

