import unittest
from dataclasses import FrozenInstanceError
from datetime import timedelta
from decimal import Decimal

from backtesting_helpers import HASH_A, HASH_B, OBSERVABLE, config, instrument
from tradepilot.backtesting.events import CompletedCandleEvent, OpeningQuoteEvent
from tradepilot.backtesting.models import CurrencyConversionObservation, InstrumentSpec
from tradepilot.backtesting.config import backtest_configuration_id
from tradepilot.backtesting.policies import FinancingModel, FinancingPolicy, RiskPolicy


class BacktestModelTests(unittest.TestCase):
    def test_domain_records_are_immutable(self) -> None:
        value = instrument()
        with self.assertRaises(FrozenInstanceError):
            value.pip_size = Decimal("0.01")  # type: ignore[misc]

    def test_instrument_pip_precision_and_quantity_validation(self) -> None:
        jpy = InstrumentSpec("USDJPY", "USD", "JPY", Decimal("0.01"), 3, Decimal("1000"))
        self.assertEqual(jpy.pip_size, Decimal("0.01"))
        with self.assertRaisesRegex(ValueError, "precision"):
            InstrumentSpec("EURUSD", "EUR", "USD", Decimal("0.00001"), 4, Decimal("1000"))
        with self.assertRaisesRegex(ValueError, "quantity_increment"):
            InstrumentSpec("EURUSD", "EUR", "USD", Decimal("0.0001"), 5, Decimal("0"))

    def test_open_event_does_not_expose_future_ohlc(self) -> None:
        event = OpeningQuoteEvent("EURUSD", "H1", OBSERVABLE, OBSERVABLE, Decimal("1.1"), Decimal("1.2"), HASH_A, HASH_B)
        self.assertFalse(hasattr(event, "bid_high"))
        self.assertFalse(hasattr(event, "ask_close"))

    def test_completed_h1_candle_is_available_only_at_close(self) -> None:
        with self.assertRaisesRegex(ValueError, "only at candle close"):
            CompletedCandleEvent(
                "EURUSD", "H1", OBSERVABLE, OBSERVABLE,
                Decimal("1"), Decimal("2"), Decimal("0.5"), Decimal("1.5"),
                Decimal("1.1"), Decimal("2.1"), Decimal("0.6"), Decimal("1.6"), HASH_A, HASH_B,
            )

    def test_configuration_requires_explicit_assumptions(self) -> None:
        self.assertEqual(config().risk_policy.max_open_positions, 1)
        with self.assertRaisesRegex(ValueError, "one position"):
            RiskPolicy("1", 2, Decimal("1000"))
        with self.assertRaisesRegex(ValueError, "requires"):
            FinancingPolicy("1", FinancingModel.EXPLICIT_RATES)

    def test_configuration_identity_is_deterministic(self) -> None:
        self.assertEqual(backtest_configuration_id(config()), backtest_configuration_id(config()))

    def test_conversion_observation_requires_timestamp_and_provenance(self) -> None:
        observation = CurrencyConversionObservation(
            "USD", "GBP", Decimal("0.8"), OBSERVABLE, "synthetic-fx", HASH_A, HASH_B,
        )
        self.assertEqual(observation.observed_at, OBSERVABLE)
        with self.assertRaisesRegex(ValueError, "positive"):
            CurrencyConversionObservation("USD", "GBP", Decimal("0"), OBSERVABLE, "source", HASH_A, HASH_B)


if __name__ == "__main__":
    unittest.main()
