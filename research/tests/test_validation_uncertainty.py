import unittest
from decimal import Decimal

from tradepilot.validation.models import UncertaintyStatus
from tradepilot.validation.uncertainty import moving_block_bootstrap


class ValidationUncertaintyTests(unittest.TestCase):
    def test_insufficient_sample_has_no_interval(self) -> None:
        value = moving_block_bootstrap((Decimal("1"),) * 10)
        self.assertIs(value.status, UncertaintyStatus.INSUFFICIENT_SAMPLE)
        self.assertIsNone(value.lower)

    def test_block_bootstrap_is_deterministic(self) -> None:
        outcomes = tuple(Decimal(index % 5 - 2) for index in range(40))
        first = moving_block_bootstrap(outcomes, resamples=100, seed_material="same")
        second = moving_block_bootstrap(outcomes, resamples=100, seed_material="same")
        self.assertEqual(first, second)
        self.assertIs(first.status, UncertaintyStatus.DEFINED)


if __name__ == "__main__": unittest.main()
