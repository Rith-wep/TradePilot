import unittest
from datetime import timedelta
from decimal import Decimal

from strategy_helpers import START, indicator_series, strategy_candle
from tradepilot.data.sessions import WeeklySessionCalendar
from tradepilot.strategies import BreakoutConfig, Direction, PriceRangeBreakoutStrategy, StrategyIndicators
from tradepilot.strategies.base import StrategyInputError


CALENDAR = WeeklySessionCalendar()


class BreakoutStrategyTests(unittest.TestCase):
    def test_valid_long_breakout_and_h1_observability(self) -> None:
        candles = [
            strategy_candle(0, "9", high="10", low="8"),
            strategy_candle(1, "10", high="11", low="9"),
            strategy_candle(2, "12", high="12.5", low="10"),
        ]
        setups = PriceRangeBreakoutStrategy(BreakoutConfig(lookback=2)).detect(
            candles, StrategyIndicators(), CALENDAR
        )
        self.assertEqual(len(setups), 1)
        self.assertEqual(setups[0].direction, Direction.LONG)
        self.assertEqual(setups[0].detection_candle_open_time, START + timedelta(hours=2))
        self.assertEqual(setups[0].observable_at, START + timedelta(hours=3))
        self.assertNotEqual(setups[0].observable_at, setups[0].detection_candle_open_time)
        self.assertEqual(setups[0].structural_invalidation_reference, Decimal("11"))

    def test_valid_short_breakout(self) -> None:
        candles = [
            strategy_candle(0, "10", high="11", low="9"),
            strategy_candle(1, "9", high="10", low="8"),
            strategy_candle(2, "7", high="9", low="6.5"),
        ]
        setups = PriceRangeBreakoutStrategy(BreakoutConfig(lookback=2)).detect(
            candles, StrategyIndicators(), CALENDAR
        )
        self.assertEqual([item.direction for item in setups], [Direction.SHORT])
        self.assertEqual(setups[0].structural_invalidation_reference, Decimal("8"))

    def test_no_breakout_on_equality(self) -> None:
        candles = [
            strategy_candle(0, "9", high="10", low="8"),
            strategy_candle(1, "10", high="11", low="9"),
            strategy_candle(2, "11", high="12", low="10"),
        ]
        self.assertEqual(
            PriceRangeBreakoutStrategy(BreakoutConfig(lookback=2)).detect(candles, StrategyIndicators(), CALENDAR),
            (),
        )

    def test_current_candle_is_excluded_from_range(self) -> None:
        candles = [
            strategy_candle(0, "9", high="10", low="8"),
            strategy_candle(1, "10", high="11", low="9"),
            strategy_candle(2, "12", high="15", low="10"),
        ]
        setups = PriceRangeBreakoutStrategy(BreakoutConfig(lookback=2)).detect(
            candles, StrategyIndicators(), CALENDAR
        )
        self.assertEqual(len(setups), 1)
        self.assertEqual(setups[0].direction, Direction.LONG)

    def test_atr_filter_rejects_unavailable_and_small_breakout(self) -> None:
        candles = [
            strategy_candle(0, "9", high="10", low="8"),
            strategy_candle(1, "10", high="11", low="9"),
            strategy_candle(2, "11.2", high="12", low="10"),
        ]
        config = BreakoutConfig(lookback=2, atr_period=2, minimum_breakout_atr=Decimal("0.5"))
        unavailable = indicator_series("ATR", 2, candles, [None, None, None])
        self.assertEqual(
            PriceRangeBreakoutStrategy(config).detect(candles, StrategyIndicators(atr=unavailable), CALENDAR),
            (),
        )
        available = indicator_series("ATR", 2, candles, [None, "1", "1"])
        self.assertEqual(
            PriceRangeBreakoutStrategy(config).detect(candles, StrategyIndicators(atr=available), CALENDAR),
            (),
        )

    def test_insufficient_lookback_returns_no_setup(self) -> None:
        candles = [strategy_candle(0, "9"), strategy_candle(1, "10")]
        self.assertEqual(
            PriceRangeBreakoutStrategy(BreakoutConfig(lookback=3)).detect(candles, StrategyIndicators(), CALENDAR),
            (),
        )

    def test_unexpected_missing_interval_is_rejected(self) -> None:
        candles = [
            strategy_candle(0, "9"),
            strategy_candle(1, "10", timestamp=START + timedelta(hours=2)),
        ]
        with self.assertRaisesRegex(StrategyInputError, "unexpected missing"):
            PriceRangeBreakoutStrategy(BreakoutConfig(lookback=1)).detect(
                candles, StrategyIndicators(), CALENDAR
            )

    def test_configuration_validation(self) -> None:
        for kwargs in ({"lookback": 0}, {"atr_period": 0}, {"minimum_breakout_atr": Decimal("-1")}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                BreakoutConfig(**kwargs)

    def test_deterministic_and_prefix_invariant(self) -> None:
        candles = [
            strategy_candle(0, "9", high="10", low="8"),
            strategy_candle(1, "10", high="11", low="9"),
            strategy_candle(2, "12", high="12.5", low="10"),
            strategy_candle(3, "10", high="11", low="9"),
        ]
        strategy = PriceRangeBreakoutStrategy(BreakoutConfig(lookback=2))
        full = strategy.detect(candles, StrategyIndicators(), CALENDAR)
        self.assertEqual(full, strategy.detect(candles, StrategyIndicators(), CALENDAR))
        for length in range(1, len(candles) + 1):
            prefix = strategy.detect(candles[:length], StrategyIndicators(), CALENDAR)
            expected = tuple(item for item in full if item.detection_candle_open_time < START + timedelta(hours=length))
            self.assertEqual(prefix, expected)


if __name__ == "__main__":
    unittest.main()

