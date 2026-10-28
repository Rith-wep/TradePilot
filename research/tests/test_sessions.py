import unittest
from datetime import date, datetime, time, timezone

from ingestion_helpers import EURUSD, raw_candle
from tradepilot.data.normalization import normalize_provider_candle
from tradepilot.data.sessions import WeeklySessionCalendar, classify_gaps


def candle_at(timestamp: datetime):
    raw = raw_candle(0, timestamp=timestamp)
    return normalize_provider_candle(
        raw, instrument=EURUSD, provider="mock", dataset_version="v1", is_synthetic=True
    )


class SessionTests(unittest.TestCase):
    def test_weekend_gap_is_expected_closure(self) -> None:
        candles = [
            candle_at(datetime(2024, 1, 5, 21, tzinfo=timezone.utc)),
            candle_at(datetime(2024, 1, 7, 22, tzinfo=timezone.utc)),
        ]
        report = classify_gaps(candles, WeeklySessionCalendar())
        self.assertEqual(report.expected_closure_count, 48)
        self.assertEqual(report.unexpected_missing_count, 0)

    def test_weekday_gap_is_unexpected(self) -> None:
        candles = [
            candle_at(datetime(2024, 1, 2, 0, tzinfo=timezone.utc)),
            candle_at(datetime(2024, 1, 2, 2, tzinfo=timezone.utc)),
        ]
        report = classify_gaps(candles, WeeklySessionCalendar())
        self.assertEqual(report.unexpected_missing_count, 1)
        self.assertEqual(report.intervals[0].classification, "unexpected_missing")

    def test_explicit_closure_date_is_configurable(self) -> None:
        calendar = WeeklySessionCalendar(closure_dates=frozenset({date(2024, 1, 2)}))
        candles = [
            candle_at(datetime(2024, 1, 2, 0, tzinfo=timezone.utc)),
            candle_at(datetime(2024, 1, 2, 2, tzinfo=timezone.utc)),
        ]
        report = classify_gaps(candles, calendar)
        self.assertEqual(report.expected_closure_count, 1)
        self.assertEqual(report.unexpected_missing_count, 0)

    def test_weekly_session_hours_are_configurable(self) -> None:
        calendar = WeeklySessionCalendar(
            open_weekday=0, open_time=time(9), close_weekday=0, close_time=time(17), name="monday-only"
        )
        self.assertFalse(calendar.is_expected_open(datetime(2024, 1, 1, 8, tzinfo=timezone.utc)))
        self.assertTrue(calendar.is_expected_open(datetime(2024, 1, 1, 12, tzinfo=timezone.utc)))
        self.assertFalse(calendar.is_expected_open(datetime(2024, 1, 1, 17, tzinfo=timezone.utc)))


if __name__ == "__main__":
    unittest.main()

