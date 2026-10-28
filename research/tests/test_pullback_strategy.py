import unittest
from datetime import timedelta

from strategy_helpers import START, indicator_series, strategy_candle
from tradepilot.data.sessions import WeeklySessionCalendar
from tradepilot.strategies import Direction, EmaRsiPullbackStrategy, PullbackConfig, StrategyIndicators


CALENDAR = WeeklySessionCalendar()


def indicators(candles, ema_values, rsi_values, atr_values):
    return StrategyIndicators(
        ema=indicator_series("EMA", 2, candles, ema_values),
        rsi=indicator_series("RSI", 2, candles, rsi_values),
        atr=indicator_series("ATR", 2, candles, atr_values),
    )


class PullbackStrategyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.strategy = EmaRsiPullbackStrategy(PullbackConfig(ema_period=2, rsi_period=2, atr_period=2))

    def test_valid_long_fresh_recovery_crossover(self) -> None:
        candles = [strategy_candle(0, "101"), strategy_candle(1, "99", low="98"), strategy_candle(2, "102")]
        supplied = indicators(candles, ["99", "100", "101"], ["40", "45", "55"], ["1", "1", "1"])
        setups = self.strategy.detect(candles, supplied, CALENDAR)
        self.assertEqual(len(setups), 1)
        self.assertEqual(setups[0].direction, Direction.LONG)
        self.assertEqual(setups[0].detection_candle_open_time, START + timedelta(hours=2))
        self.assertEqual(setups[0].observable_at, START + timedelta(hours=3))
        self.assertEqual(str(setups[0].structural_invalidation_reference), "97")

    def test_valid_short_fresh_recovery_crossover(self) -> None:
        candles = [strategy_candle(0, "99"), strategy_candle(1, "101", high="102"), strategy_candle(2, "98")]
        supplied = indicators(candles, ["101", "100", "99"], ["60", "55", "45"], ["1", "1", "1"])
        setups = self.strategy.detect(candles, supplied, CALENDAR)
        self.assertEqual([item.direction for item in setups], [Direction.SHORT])
        self.assertEqual(str(setups[0].structural_invalidation_reference), "103")

    def test_consecutive_candle_does_not_repeat_signal_without_fresh_cross(self) -> None:
        candles = [
            strategy_candle(0, "101"), strategy_candle(1, "99"),
            strategy_candle(2, "102"), strategy_candle(3, "103"),
        ]
        supplied = indicators(
            candles, ["99", "100", "101", "102"],
            ["40", "45", "55", "60"], ["1", "1", "1", "1"],
        )
        setups = self.strategy.detect(candles, supplied, CALENDAR)
        self.assertEqual(len(setups), 1)
        self.assertEqual(setups[0].detection_candle_open_time, START + timedelta(hours=2))

    def test_rejects_when_previous_candle_did_not_cross_from_other_side(self) -> None:
        candles = [strategy_candle(0, "99"), strategy_candle(1, "101"), strategy_candle(2, "103")]
        supplied = indicators(candles, ["99", "100", "102"], ["40", "45", "55"], ["1", "1", "1"])
        self.assertEqual(self.strategy.detect(candles, supplied, CALENDAR), ())

    def test_required_indicator_warmup_suppresses_setup(self) -> None:
        candles = [strategy_candle(0, "101"), strategy_candle(1, "99"), strategy_candle(2, "102")]
        supplied = indicators(candles, ["99", "100", "101"], ["40", "45", None], ["1", "1", "1"])
        self.assertEqual(self.strategy.detect(candles, supplied, CALENDAR), ())

    def test_insufficient_history_returns_no_setup(self) -> None:
        candles = [strategy_candle(0, "101")]
        supplied = indicators(candles, ["99"], ["40"], ["1"])
        self.assertEqual(self.strategy.detect(candles, supplied, CALENDAR), ())

    def test_configuration_validation(self) -> None:
        for kwargs in ({"ema_period": 0}, {"rsi_period": 0}, {"atr_period": 0}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                PullbackConfig(**kwargs)

    def test_deterministic_and_prefix_invariant(self) -> None:
        candles = [
            strategy_candle(0, "101"), strategy_candle(1, "99"),
            strategy_candle(2, "102"), strategy_candle(3, "103"),
        ]
        supplied = indicators(
            candles, ["99", "100", "101", "102"],
            ["40", "45", "55", "60"], ["1", "1", "1", "1"],
        )
        full = self.strategy.detect(candles, supplied, CALENDAR)
        self.assertEqual(full, self.strategy.detect(candles, supplied, CALENDAR))
        for length in range(1, len(candles) + 1):
            prefix_indicators = indicators(
                candles[:length],
                ["99", "100", "101", "102"][:length],
                ["40", "45", "55", "60"][:length],
                ["1", "1", "1", "1"][:length],
            )
            prefix = self.strategy.detect(candles[:length], prefix_indicators, CALENDAR)
            expected = tuple(item for item in full if item.detection_candle_open_time < START + timedelta(hours=length))
            self.assertEqual(prefix, expected)


if __name__ == "__main__":
    unittest.main()
