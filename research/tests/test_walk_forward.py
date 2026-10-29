import unittest

from validation_helpers import candles
from tradepilot.validation.models import WalkForwardPolicy
from tradepilot.validation.partitions import chronological_partitions
from tradepilot.validation.walk_forward import expanding_folds


class WalkForwardTests(unittest.TestCase):
    def test_expanding_training_and_nonoverlapping_validation(self) -> None:
        values = candles(100)
        training = chronological_partitions(values, "a" * 64)[0]
        folds = expanding_folds(values, training, "a" * 64, WalkForwardPolicy(20, 10, 10, 1))
        self.assertGreater(len(folds), 1)
        self.assertLess(folds[0].training.candle_count, folds[1].training.candle_count)
        self.assertEqual(folds[0].validation.end, folds[1].validation.start)

    def test_overlapping_policy_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "overlapping"):
            WalkForwardPolicy(20, 10, 5)


if __name__ == "__main__": unittest.main()
