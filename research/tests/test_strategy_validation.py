import unittest
from dataclasses import replace
from datetime import timedelta

from strategy_helpers import START, indicator_series, strategy_candle
from tradepilot.data.sessions import WeeklySessionCalendar
from tradepilot.strategies import EmaRsiPullbackStrategy, PullbackConfig, StrategyIndicators
from tradepilot.strategies.base import StrategyInputError, configuration_fingerprint
from tradepilot.strategies.models import deduplicate_setups


class StrategyValidationTests(unittest.TestCase):
    def test_misaligned_indicator_timestamp_is_rejected(self) -> None:
        candles = [strategy_candle(0, "101"), strategy_candle(1, "99")]
        ema = indicator_series("EMA", 1, candles, ["100", "100"])
        ema = replace(
            ema,
            points=(ema.points[0], replace(ema.points[1], timestamp=ema.points[1].timestamp + timedelta(hours=1))),
        )
        supplied = StrategyIndicators(
            ema=ema,
            rsi=indicator_series("RSI", 1, candles, ["40", "55"]),
            atr=indicator_series("ATR", 1, candles, ["1", "1"]),
        )
        strategy = EmaRsiPullbackStrategy(PullbackConfig(ema_period=1, rsi_period=1, atr_period=1))
        with self.assertRaisesRegex(StrategyInputError, "timestamps do not align"):
            strategy.detect(candles, supplied, WeeklySessionCalendar())

    def test_configuration_fingerprint_is_deterministic(self) -> None:
        config = PullbackConfig()
        calendar = WeeklySessionCalendar()
        first = configuration_fingerprint("strategy", "1", config, calendar.calendar_id)
        second = configuration_fingerprint("strategy", "1", config, calendar.calendar_id)
        self.assertEqual(first, second)
        self.assertEqual(len(first), 64)

    def test_duplicate_prevention_returns_one_identical_setup(self) -> None:
        candles = [strategy_candle(0, "101"), strategy_candle(1, "99"), strategy_candle(2, "102")]
        supplied = StrategyIndicators(
            ema=indicator_series("EMA", 2, candles, ["99", "100", "101"]),
            rsi=indicator_series("RSI", 2, candles, ["40", "45", "55"]),
            atr=indicator_series("ATR", 2, candles, ["1", "1", "1"]),
        )
        setup = EmaRsiPullbackStrategy(
            PullbackConfig(ema_period=2, rsi_period=2, atr_period=2)
        ).detect(candles, supplied, WeeklySessionCalendar())[0]
        self.assertEqual(deduplicate_setups([setup, setup]), (setup,))

    def test_setup_is_not_observable_at_open(self) -> None:
        candles = [strategy_candle(0, "101"), strategy_candle(1, "99"), strategy_candle(2, "102")]
        supplied = StrategyIndicators(
            ema=indicator_series("EMA", 2, candles, ["99", "100", "101"]),
            rsi=indicator_series("RSI", 2, candles, ["40", "45", "55"]),
            atr=indicator_series("ATR", 2, candles, ["1", "1", "1"]),
        )
        setup = EmaRsiPullbackStrategy(
            PullbackConfig(ema_period=2, rsi_period=2, atr_period=2)
        ).detect(candles, supplied, WeeklySessionCalendar())[0]
        self.assertEqual(setup.detection_candle_open_time, START + timedelta(hours=2))
        self.assertEqual(setup.observable_at, START + timedelta(hours=3))
        self.assertGreater(setup.observable_at, setup.detection_candle_open_time)


if __name__ == "__main__":
    unittest.main()

