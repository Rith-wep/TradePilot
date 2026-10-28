import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from ingestion_helpers import EURUSD
from tradepilot.data.models import Candle
from tradepilot.indicators import IndicatorInputError, atr, ema, rsi


START = datetime(2024, 1, 1, tzinfo=timezone.utc)


def candle(index: int, close: str, high: str | None = None, low: str | None = None) -> Candle:
    close_value = Decimal(close)
    high_value = Decimal(high) if high is not None else close_value
    low_value = Decimal(low) if low is not None else close_value
    return Candle(
        instrument=EURUSD,
        timestamp=START + timedelta(hours=index),
        timeframe="H1",
        bid_open=close_value,
        bid_high=high_value,
        bid_low=low_value,
        bid_close=close_value,
        ask_open=close_value,
        ask_high=high_value,
        ask_low=low_value,
        ask_close=close_value,
        source="indicator-test-synthetic",
        dataset_version="v1",
        is_synthetic=True,
    )


def close_candles(values: list[str]) -> list[Candle]:
    return [candle(index, value) for index, value in enumerate(values)]


class IndicatorTests(unittest.TestCase):
    def test_ema_known_reference_values(self) -> None:
        series = ema(close_candles(["1", "2", "3", "4", "5"]), 3, "bid")
        self.assertEqual([point.value for point in series.points], [None, None, Decimal("2"), Decimal("3"), Decimal("4")])

    def test_rsi_wilder_known_reference_value(self) -> None:
        closes = [
            "44.34", "44.09", "44.15", "43.61", "44.33",
            "44.83", "45.10", "45.42", "45.84", "46.08",
            "45.89", "46.03", "45.61", "46.28", "46.28",
        ]
        value = rsi(close_candles(closes), 14, "bid").points[-1].value
        self.assertIsNotNone(value)
        self.assertEqual(value.quantize(Decimal("0.000001")), Decimal("70.464135"))  # type: ignore[union-attr]

    def test_atr_wilder_known_reference_values(self) -> None:
        candles = [
            candle(0, "9", "10", "8"),
            candle(1, "11", "12", "9"),
            candle(2, "12", "13", "10"),
            candle(3, "14", "15", "11"),
        ]
        values = [point.value for point in atr(candles, 3, "bid").points]
        self.assertEqual(values[:2], [None, None])
        self.assertEqual(values[2].quantize(Decimal("0.000001")), Decimal("2.666667"))  # type: ignore[union-attr]
        self.assertEqual(values[3].quantize(Decimal("0.000001")), Decimal("3.111111"))  # type: ignore[union-attr]

    def test_insufficient_history_returns_aligned_warmup(self) -> None:
        candles = close_candles(["1", "2"])
        self.assertEqual([point.value for point in ema(candles, 3).points], [None, None])
        self.assertEqual([point.value for point in rsi(candles, 3).points], [None, None])
        self.assertEqual([point.value for point in atr(candles, 3).points], [None, None])

    def test_constant_prices(self) -> None:
        candles = close_candles(["5", "5", "5", "5"])
        self.assertEqual(ema(candles, 3).points[-1].value, Decimal("5"))
        self.assertEqual(rsi(candles, 3).points[-1].value, Decimal("50"))
        self.assertEqual(atr(candles, 3).points[-1].value, Decimal("0"))

    def test_bid_ask_and_mid_price_selection(self) -> None:
        candles = [
            replace(
                item,
                ask_open=item.bid_open + Decimal("2"),
                ask_high=item.bid_high + Decimal("2"),
                ask_low=item.bid_low + Decimal("2"),
                ask_close=item.bid_close + Decimal("2"),
            )
            for item in close_candles(["1", "2", "3"])
        ]
        self.assertEqual(ema(candles, 3, "bid").points[-1].value, Decimal("2"))
        self.assertEqual(ema(candles, 3, "ask").points[-1].value, Decimal("4"))
        self.assertEqual(ema(candles, 3, "mid").points[-1].value, Decimal("3"))

    def test_invalid_parameters_are_rejected(self) -> None:
        candles = close_candles(["1"])
        for invalid in (0, -1, True, 1.5):
            with self.subTest(period=invalid), self.assertRaises(IndicatorInputError):
                ema(candles, invalid)  # type: ignore[arg-type]
        with self.assertRaises(IndicatorInputError):
            ema(candles, 1, "last")  # type: ignore[arg-type]

    def test_missing_and_invalid_input_are_rejected(self) -> None:
        with self.assertRaises(TypeError):
            ema(None, 3)  # type: ignore[arg-type]
        candles = close_candles(["1", "2"])
        duplicate = replace(candles[1], timestamp=candles[0].timestamp)
        with self.assertRaisesRegex(IndicatorInputError, "duplicate_timestamp"):
            rsi([candles[0], duplicate], 1)
        invalid_price = replace(candles[0], bid_close=None)  # type: ignore[arg-type]
        with self.assertRaisesRegex(IndicatorInputError, "finite Decimal"):
            atr([invalid_price], 1)

    def test_repeated_calculations_are_deterministic(self) -> None:
        candles = close_candles(["1", "2", "1", "3", "2", "4"])
        self.assertEqual(ema(candles, 3), ema(candles, 3))
        self.assertEqual(rsi(candles, 3), rsi(candles, 3))
        self.assertEqual(atr(candles, 3), atr(candles, 3))

    def test_prefix_results_prove_no_future_data_leakage(self) -> None:
        candles = close_candles(["1", "2", "1", "3", "2", "4", "3"])
        for function in (ema, rsi, atr):
            full = function(candles, 3)
            for length in range(1, len(candles) + 1):
                prefix = function(candles[:length], 3)
                self.assertEqual(prefix.points, full.points[:length])

    def test_empty_input_returns_empty_series(self) -> None:
        self.assertEqual(ema([], 3).points, ())
        self.assertEqual(rsi([], 3).points, ())
        self.assertEqual(atr([], 3).points, ())


if __name__ == "__main__":
    unittest.main()

