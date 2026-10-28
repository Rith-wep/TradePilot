import unittest
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

from tradepilot.data.csv_loader import load_candles_csv
from tradepilot.data.models import Instrument
from tradepilot.data.validation import validate_candles


ROOT = Path(__file__).resolve().parents[1]
EURUSD = Instrument("EURUSD", "EUR", "USD", Decimal("0.0001"), 5)


class ValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.candles = load_candles_csv(ROOT / "fixtures/synthetic_eurusd_h1.csv", EURUSD)

    def test_valid_fixture_has_stable_summary(self) -> None:
        report = validate_candles(self.candles)
        self.assertTrue(report.valid)
        self.assertEqual(report.candle_count, 5)
        self.assertEqual(report.error_count, 0)
        self.assertEqual(report.warning_count, 0)
        self.assertEqual(report.first_timestamp, "2024-01-02T00:00:00Z")

    def test_detects_duplicate_and_bid_above_ask(self) -> None:
        invalid = replace(
            self.candles[1],
            timestamp=self.candles[0].timestamp,
            bid_open=Decimal("1.20000"),
        )
        report = validate_candles([self.candles[0], invalid])
        codes = {issue.code for issue in report.issues}
        self.assertFalse(report.valid)
        self.assertIn("duplicate_timestamp", codes)
        self.assertIn("bid_above_ask", codes)

    def test_detects_out_of_order_and_invalid_ohlc(self) -> None:
        invalid = replace(
            self.candles[1],
            timestamp=self.candles[0].timestamp - timedelta(hours=1),
            bid_low=Decimal("1.30000"),
        )
        report = validate_candles([self.candles[0], invalid])
        codes = {issue.code for issue in report.issues}
        self.assertIn("out_of_order", codes)
        self.assertIn("invalid_bid_ohlc", codes)

    def test_reports_gap_without_fabricating_data(self) -> None:
        later = replace(self.candles[1], timestamp=self.candles[0].timestamp + timedelta(hours=3))
        report = validate_candles([self.candles[0], later])
        self.assertTrue(report.valid)
        self.assertEqual(report.warning_count, 1)
        self.assertEqual(report.issues[0].code, "time_gap")


if __name__ == "__main__":
    unittest.main()

