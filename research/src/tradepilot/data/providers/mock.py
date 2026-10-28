"""Deterministic provider used for local development and tests."""

from collections.abc import Sequence

from tradepilot.data.providers.base import (
    ProviderCandle,
    ProviderPage,
    ProviderRequest,
    TransientProviderError,
)


class MockMarketDataProvider:
    def __init__(
        self,
        candles: Sequence[ProviderCandle],
        *,
        page_size: int = 500,
        failures_before_success: int = 0,
        name: str = "mock",
        dataset_version: str = "mock-v1",
    ) -> None:
        if page_size <= 0:
            raise ValueError("page_size must be positive")
        self._candles = tuple(candles)
        self._page_size = page_size
        self._remaining_failures = failures_before_success
        self._name = name
        self._dataset_version = dataset_version
        self.calls = 0

    @property
    def name(self) -> str:
        return self._name

    @property
    def dataset_version(self) -> str:
        return self._dataset_version

    @property
    def is_synthetic(self) -> bool:
        return True

    def fetch_page(self, request: ProviderRequest, cursor: str | None = None) -> ProviderPage:
        self.calls += 1
        if self._remaining_failures:
            self._remaining_failures -= 1
            raise TransientProviderError("configured mock transient failure")
        offset = int(cursor) if cursor is not None else 0
        matching = [
            candle
            for candle in self._candles
            if request.start <= candle.timestamp < request.end
            and candle.timeframe == request.timeframe
        ]
        page = matching[offset : offset + self._page_size]
        next_offset = offset + len(page)
        next_cursor = str(next_offset) if next_offset < len(matching) else None
        return ProviderPage(page, next_cursor, {"adapter": "deterministic-mock"})

