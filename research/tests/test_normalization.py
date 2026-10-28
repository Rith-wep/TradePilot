import unittest
from datetime import datetime, timedelta, timezone

from ingestion_helpers import EURUSD, raw_candle
from tradepilot.data.normalization import NormalizationError, normalize_provider_candle


class NormalizationTests(unittest.TestCase):
    def test_converts_aware_timestamp_to_utc(self) -> None:
        offset = timezone(timedelta(hours=5, minutes=30))
        raw = raw_candle(0, timestamp=datetime(2024, 1, 2, 5, 30, tzinfo=offset))
        candle = normalize_provider_candle(
            raw, instrument=EURUSD, provider="mock", dataset_version="v1", is_synthetic=True
        )
        self.assertEqual(candle.timestamp, datetime(2024, 1, 2, tzinfo=timezone.utc))
        self.assertEqual(candle.timestamp.utcoffset(), timedelta(0))

    def test_rejects_naive_timestamp(self) -> None:
        with self.assertRaisesRegex(NormalizationError, "timezone-aware"):
            normalize_provider_candle(
                raw_candle(0, timestamp=datetime(2024, 1, 2)),
                instrument=EURUSD,
                provider="mock",
                dataset_version="v1",
                is_synthetic=True,
            )

    def test_rejects_incomplete_candle(self) -> None:
        with self.assertRaisesRegex(NormalizationError, "incomplete"):
            normalize_provider_candle(
                raw_candle(0, complete=False),
                instrument=EURUSD,
                provider="mock",
                dataset_version="v1",
                is_synthetic=True,
            )

    def test_rejects_non_finite_price(self) -> None:
        with self.assertRaisesRegex(NormalizationError, "finite decimals"):
            normalize_provider_candle(
                raw_candle(0, bid_open="NaN"),
                instrument=EURUSD,
                provider="mock",
                dataset_version="v1",
                is_synthetic=True,
            )


if __name__ == "__main__":
    unittest.main()

