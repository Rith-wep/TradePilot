import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from tradepilot.data.csv_loader import CandleLoadError, load_candles_csv
from tradepilot.data.models import Instrument


RESEARCH_ROOT = Path(__file__).resolve().parents[1]
EURUSD = Instrument("EURUSD", "EUR", "USD", Decimal("0.0001"), 5)


class LoaderTests(unittest.TestCase):
    def test_loads_synthetic_fixture_with_decimal_prices(self) -> None:
        candles = load_candles_csv(RESEARCH_ROOT / "fixtures/synthetic_eurusd_h1.csv", EURUSD)
        self.assertEqual(len(candles), 5)
        self.assertEqual(candles[0].bid_open, Decimal("1.10000"))
        self.assertTrue(all(candle.is_synthetic for candle in candles))

    def test_rejects_missing_columns(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.csv"
            path.write_text("timestamp,symbol\n2024-01-01T00:00:00Z,EURUSD\n", encoding="utf-8")
            with self.assertRaisesRegex(CandleLoadError, "missing required columns"):
                load_candles_csv(path, EURUSD)


if __name__ == "__main__":
    unittest.main()

