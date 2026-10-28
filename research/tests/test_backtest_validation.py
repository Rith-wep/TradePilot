import unittest
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

from backtesting_helpers import HASH_A, HASH_B, HASH_C, HASH_D, OBSERVABLE, config
from tradepilot.backtesting.models import BacktestProvenance, CurrencyConversionObservation
from tradepilot.backtesting.validation import validate_conversion_observation, validate_order_configuration, validate_provenance
from backtesting_helpers import order
from tradepilot.reporting.models import ResearchContent
from tradepilot.reporting.storage import report_identifier


def report_content() -> ResearchContent:
    return ResearchContent(
        "tradepilot-candidate-report-v1", HASH_A, HASH_B, "EURUSD", "H1",
        OBSERVABLE - timedelta(hours=3), OBSERVABLE, "strategy", "1.0.0", HASH_D,
        (), (), "calendar-v1", True, "research/1", "report-revision", (),
    )


class BacktestValidationTests(unittest.TestCase):
    def test_matching_provenance_is_accepted(self) -> None:
        integrity = SimpleNamespace(valid=True, dataset_id=HASH_A, dataset_checksum=HASH_B)
        report = report_content()
        report_id = report_identifier(report)
        provenance = BacktestProvenance(HASH_A, HASH_B, report_id, "strategy", "1.0.0", HASH_D, "revision")
        validate_provenance(config(provenance_value=provenance), integrity, report_id, report)

    def test_provenance_mismatch_is_rejected(self) -> None:
        integrity = SimpleNamespace(valid=True, dataset_id=HASH_A, dataset_checksum=HASH_B)
        report = report_content()
        report_id = report_identifier(report)
        provenance = BacktestProvenance(HASH_A, HASH_B, report_id, "other", "1.0.0", HASH_D, "revision")
        with self.assertRaisesRegex(ValueError, "strategy name"):
            validate_provenance(config(provenance_value=provenance), integrity, report_id, report)

    def test_noncanonical_report_id_is_rejected(self) -> None:
        integrity = SimpleNamespace(valid=True, dataset_id=HASH_A, dataset_checksum=HASH_B)
        with self.assertRaisesRegex(ValueError, "canonical"):
            validate_provenance(config(), integrity, HASH_C, report_content())

    def test_matching_account_and_quote_currency_needs_no_conversion(self) -> None:
        validate_conversion_observation(config(), None, OBSERVABLE)
        observation = CurrencyConversionObservation("USD", "GBP", Decimal("0.8"), OBSERVABLE, "synthetic", HASH_A, HASH_B)
        with self.assertRaisesRegex(ValueError, "unnecessary"):
            validate_conversion_observation(config(), observation, OBSERVABLE)

    def test_cross_currency_requires_nonfuture_compatible_observation(self) -> None:
        cross_config = config(account_currency="GBP")
        current = CurrencyConversionObservation("USD", "GBP", Decimal("0.8"), OBSERVABLE, "synthetic", HASH_A, HASH_B)
        validate_conversion_observation(cross_config, current, OBSERVABLE)
        future = CurrencyConversionObservation("USD", "GBP", Decimal("0.8"), OBSERVABLE + timedelta(hours=1), "synthetic", HASH_A, HASH_B)
        with self.assertRaisesRegex(ValueError, "future"):
            validate_conversion_observation(cross_config, future, OBSERVABLE)
        with self.assertRaisesRegex(ValueError, "requires"):
            validate_conversion_observation(cross_config, None, OBSERVABLE)

    def test_order_quantity_respects_instrument_and_risk_configuration(self) -> None:
        validate_order_configuration(order(), config())
        with self.assertRaisesRegex(ValueError, "increment"):
            validate_order_configuration(order(quantity=Decimal("10001")), config())
        with self.assertRaisesRegex(ValueError, "maximum"):
            validate_order_configuration(order(quantity=Decimal("101000")), config())


if __name__ == "__main__":
    unittest.main()
