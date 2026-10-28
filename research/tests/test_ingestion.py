import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ingestion_helpers import EURUSD, START, raw_candle
from tradepilot.data.ingestion import HistoricalIngestor, IngestionConfig, IngestionError
from tradepilot.data.providers.base import ProviderError, ProviderPage
from tradepilot.data.providers.mock import MockMarketDataProvider
from tradepilot.data.storage import ParquetDatasetStore


FIXED_NOW = datetime(2024, 2, 1, tzinfo=timezone.utc)


class PermanentFailureProvider(MockMarketDataProvider):
    def fetch_page(self, request, cursor=None):
        raise ProviderError("permanent failure")


class TimeoutProvider(MockMarketDataProvider):
    def fetch_page(self, request, cursor=None):
        self.calls += 1
        if self.calls < 3:
            raise TimeoutError("timed out")
        return ProviderPage([raw_candle(0)])


class IngestionTests(unittest.TestCase):
    def ingest(self, provider, *, end=START + timedelta(hours=3), config=None):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        sleeps: list[float] = []
        ingestor = HistoricalIngestor(
            provider,
            ParquetDatasetStore(temporary.name),
            config=config,
            clock=lambda: FIXED_NOW,
            sleeper=sleeps.append,
        )
        return ingestor.ingest(EURUSD, "H1", START, end), sleeps

    def test_successful_paginated_mock_ingestion(self) -> None:
        result, _ = self.ingest(MockMarketDataProvider([raw_candle(i) for i in range(3)], page_size=1))
        self.assertEqual(result.fetched_count, 3)
        self.assertEqual(result.stored.row_count, 3)
        self.assertTrue(result.quality_report.valid)

    def test_deduplicates_identical_provider_candles(self) -> None:
        result, _ = self.ingest(MockMarketDataProvider([raw_candle(0), raw_candle(0), raw_candle(1)]))
        self.assertEqual(result.fetched_count, 3)
        self.assertEqual(result.unique_count, 2)
        self.assertEqual(result.duplicate_count, 1)

    def test_missing_interval_is_quality_warning(self) -> None:
        result, _ = self.ingest(MockMarketDataProvider([raw_candle(0), raw_candle(2)]))
        self.assertTrue(result.quality_report.valid)
        self.assertEqual(result.quality_report.issues[0].code, "time_gap")

    def test_rejects_invalid_ohlc_and_bid_ask(self) -> None:
        invalid = raw_candle(0, bid_open="1.50000")
        with self.assertRaisesRegex(IngestionError, "failed validation"):
            self.ingest(MockMarketDataProvider([invalid]), end=START + timedelta(hours=1))

    def test_retries_transient_errors_with_exponential_backoff(self) -> None:
        provider = MockMarketDataProvider([raw_candle(0)], failures_before_success=2)
        result, sleeps = self.ingest(
            provider,
            end=START + timedelta(hours=1),
            config=IngestionConfig(max_retries=2, retry_backoff_seconds=0.25),
        )
        self.assertEqual(result.retry_count, 2)
        self.assertEqual(sleeps, [0.25, 0.5])

    def test_retries_timeouts(self) -> None:
        result, _ = self.ingest(
            TimeoutProvider([]),
            end=START + timedelta(hours=1),
            config=IngestionConfig(max_retries=2, retry_backoff_seconds=0),
        )
        self.assertEqual(result.retry_count, 2)

    def test_does_not_retry_permanent_provider_error(self) -> None:
        with self.assertRaisesRegex(IngestionError, "provider request failed"):
            self.ingest(PermanentFailureProvider([]), end=START + timedelta(hours=1))

    def test_raises_after_retry_limit(self) -> None:
        with self.assertRaisesRegex(IngestionError, "after 2 attempts"):
            self.ingest(
                MockMarketDataProvider([raw_candle(0)], failures_before_success=3),
                end=START + timedelta(hours=1),
                config=IngestionConfig(max_retries=1, retry_backoff_seconds=0),
            )


if __name__ == "__main__":
    unittest.main()

