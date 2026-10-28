import unittest
from dataclasses import replace

from accounting_helpers import accounting_context
from tradepilot.accounting.engine import AccountingError, build_accounting


class AccountingReproducibilityTests(unittest.TestCase):
    def test_identical_inputs_have_identical_report_ids(self) -> None:
        result, simulation, config = accounting_context(stop_pips="10", holding=2)
        first = build_accounting(result, simulation, config)
        second = build_accounting(result, simulation, config)
        self.assertEqual(first, second)

    def test_provenance_mismatch_is_rejected(self) -> None:
        result, simulation, config = accounting_context()
        broken = replace(result, configuration_id="f" * 64)
        with self.assertRaisesRegex(AccountingError, "provenance"):
            build_accounting(broken, simulation, config)

    def test_commission_currency_must_be_explicit_assumption(self) -> None:
        result, simulation, config = accounting_context()
        with self.assertRaisesRegex(AccountingError, "explicit assumption"):
            build_accounting(result, simulation, replace(config, commission_currency_is_assumption=False))


if __name__ == "__main__":
    unittest.main()
