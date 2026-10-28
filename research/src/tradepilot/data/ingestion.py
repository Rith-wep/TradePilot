"""Historical range ingestion with batching, retries, validation, and storage."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from time import sleep

from tradepilot.data.models import Candle, Instrument
from tradepilot.data.normalization import NormalizationError, normalize_provider_candle
from tradepilot.data.providers.base import (
    MarketDataProvider,
    ProviderError,
    ProviderRequest,
    RateLimitError,
    TransientProviderError,
)
from tradepilot.data.storage import ParquetDatasetStore, StoredDataset
from tradepilot.data.validation import QualityReport, validate_candles


class IngestionError(RuntimeError):
    """Raised when retrieval, normalization, or validation cannot complete."""


@dataclass(frozen=True, slots=True)
class IngestionConfig:
    batch_duration: timedelta = timedelta(days=90)
    request_timeout_seconds: float = 30.0
    max_retries: int = 3
    retry_backoff_seconds: float = 1.0

    def __post_init__(self) -> None:
        if self.batch_duration <= timedelta(0):
            raise ValueError("batch_duration must be positive")
        if self.request_timeout_seconds <= 0:
            raise ValueError("request_timeout_seconds must be positive")
        if self.max_retries < 0 or self.retry_backoff_seconds < 0:
            raise ValueError("retry settings must not be negative")


@dataclass(frozen=True, slots=True)
class IngestionResult:
    fetched_count: int
    unique_count: int
    duplicate_count: int
    retry_count: int
    quality_report: QualityReport
    stored: StoredDataset


def _require_utc_range(start: datetime, end: datetime) -> None:
    for name, value in (("start", start), ("end", end)):
        if value.tzinfo is None or value.utcoffset() != timedelta(0):
            raise ValueError(f"{name} must be UTC-aware")
    if start >= end:
        raise ValueError("start must be earlier than end")


class HistoricalIngestor:
    def __init__(
        self,
        provider: MarketDataProvider,
        store: ParquetDatasetStore,
        *,
        config: IngestionConfig | None = None,
        clock: Callable[[], datetime] | None = None,
        sleeper: Callable[[float], None] = sleep,
    ) -> None:
        self.provider = provider
        self.store = store
        self.config = config or IngestionConfig()
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.sleeper = sleeper

    def _fetch_with_retry(self, request: ProviderRequest, cursor: str | None):
        retries = 0
        while True:
            try:
                return self.provider.fetch_page(request, cursor), retries
            except (TimeoutError, TransientProviderError) as exc:
                if retries >= self.config.max_retries:
                    raise IngestionError(
                        f"provider failed after {retries + 1} attempts: {exc}"
                    ) from exc
                delay = (
                    exc.retry_after_seconds
                    if isinstance(exc, RateLimitError) and exc.retry_after_seconds is not None
                    else self.config.retry_backoff_seconds * (2 ** retries)
                )
                retries += 1
                self.sleeper(delay)
            except ProviderError as exc:
                raise IngestionError(f"provider request failed: {exc}") from exc

    def ingest(
        self,
        instrument: Instrument,
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> IngestionResult:
        _require_utc_range(start, end)
        raw_candles = []
        retries = 0
        metadata: dict[str, str] = {}
        batch_start = start
        while batch_start < end:
            batch_end = min(batch_start + self.config.batch_duration, end)
            request = ProviderRequest(
                instrument,
                timeframe,
                batch_start,
                batch_end,
                self.config.request_timeout_seconds,
            )
            cursor: str | None = None
            seen_cursors: set[str] = set()
            while True:
                page, page_retries = self._fetch_with_retry(request, cursor)
                retries += page_retries
                raw_candles.extend(page.candles)
                metadata.update(page.metadata or {})
                if page.next_cursor is None:
                    break
                if page.next_cursor in seen_cursors:
                    raise IngestionError("provider returned a repeated pagination cursor")
                seen_cursors.add(page.next_cursor)
                cursor = page.next_cursor
            batch_start = batch_end

        normalized: list[Candle] = []
        try:
            for raw in raw_candles:
                candle = normalize_provider_candle(
                    raw,
                    instrument=instrument,
                    provider=self.provider.name,
                    dataset_version=self.provider.dataset_version,
                    is_synthetic=self.provider.is_synthetic,
                )
                if not start <= candle.timestamp < end:
                    raise NormalizationError("provider returned a candle outside the requested range")
                normalized.append(candle)
        except NormalizationError as exc:
            raise IngestionError(f"invalid provider response: {exc}") from exc

        normalized.sort(key=lambda candle: candle.timestamp)
        unique_by_timestamp: dict[datetime, Candle] = {}
        for candle in normalized:
            existing = unique_by_timestamp.get(candle.timestamp)
            if existing is not None and existing != candle:
                raise IngestionError(
                    f"provider returned conflicting candles at {candle.timestamp.isoformat()}"
                )
            unique_by_timestamp[candle.timestamp] = candle
        unique = list(unique_by_timestamp.values())
        report = validate_candles(unique)
        if not report.valid:
            codes = ", ".join(issue.code for issue in report.issues if issue.severity == "error")
            raise IngestionError(f"provider data failed validation: {codes}")
        retrieved_at = self.clock()
        if retrieved_at.tzinfo is None or retrieved_at.utcoffset() is None:
            raise IngestionError("retrieval clock must return a timezone-aware timestamp")
        metadata.update({
            "dataset_version": self.provider.dataset_version,
            "is_synthetic": str(self.provider.is_synthetic).lower(),
        })
        stored = self.store.save(
            self.provider.name,
            instrument,
            timeframe,
            unique,
            retrieved_at=retrieved_at,
            request_start=start,
            request_end=end,
            provider_metadata=metadata,
        )
        return IngestionResult(
            fetched_count=len(normalized),
            unique_count=len(unique),
            duplicate_count=len(normalized) - len(unique),
            retry_count=retries,
            quality_report=report,
            stored=stored,
        )

