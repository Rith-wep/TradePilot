import unittest
from datetime import timedelta
from decimal import Decimal

from accounting_helpers import accounting_context
from simulator_helpers import HASH_A, HASH_B, START
from tradepilot.accounting.conversion import ConversionError, convert
from tradepilot.backtesting.models import CurrencyConversionObservation
from dataclasses import replace
from tradepilot.accounting.engine import build_accounting
from tradepilot.accounting.models import AccountingConfig


class CurrencyConversionTests(unittest.TestCase):
    def test_identity_direct_and_reciprocal_conversion(self) -> None:
        direct = CurrencyConversionObservation("USD", "GBP", Decimal("0.8"), START, "synthetic", HASH_A, HASH_B)
        reciprocal = CurrencyConversionObservation("GBP", "USD", Decimal("1.25"), START, "synthetic", HASH_A, HASH_B)
        self.assertEqual(convert(Decimal("100"), "USD", "USD", START, (), timedelta(hours=1)).converted_amount, Decimal("100"))
        self.assertEqual(convert(Decimal("100"), "USD", "GBP", START, (direct,), timedelta(hours=1)).converted_amount, Decimal("80.0"))
        self.assertEqual(convert(Decimal("100"), "USD", "GBP", START, (reciprocal,), timedelta(hours=1)).converted_amount, Decimal("8E+1"))

    def test_future_stale_missing_and_conflicting_rates_are_rejected(self) -> None:
        future = CurrencyConversionObservation("USD", "GBP", Decimal("0.8"), START + timedelta(hours=1), "synthetic", HASH_A, HASH_B)
        with self.assertRaises(ConversionError):
            convert(Decimal("1"), "USD", "GBP", START, (future,), timedelta(hours=1))
        stale = CurrencyConversionObservation("USD", "GBP", Decimal("0.8"), START, "synthetic", HASH_A, HASH_B)
        with self.assertRaises(ConversionError):
            convert(Decimal("1"), "USD", "GBP", START + timedelta(hours=2), (stale,), timedelta(hours=1))
        conflict = CurrencyConversionObservation("USD", "GBP", Decimal("0.9"), START, "other", HASH_A, HASH_B)
        with self.assertRaisesRegex(ConversionError, "conflicting"):
            convert(Decimal("1"), "USD", "GBP", START, (stale, conflict), timedelta(hours=1))

    def test_accounting_preserves_quote_pnl_and_converts_only_account_values(self) -> None:
        result, simulation, _ = accounting_context(holding=1)
        config = AccountingConfig("GBP", Decimal("10000"), "USD", True, timedelta(hours=24))
        observation = CurrencyConversionObservation("USD", "GBP", Decimal("0.8"), START, "synthetic", HASH_A, HASH_B)
        report = build_accounting(result, simulation, config, (observation,)).content
        trade = report.trades[0]
        self.assertEqual(trade.gross_pnl_account, trade.gross_pnl_quote * Decimal("0.8"))
        self.assertEqual(report.used_conversion_observations, (observation,))


if __name__ == "__main__":
    unittest.main()
