import unittest

from validation_helpers import candles
from tradepilot.validation.models import PartitionName
from tradepilot.validation.partitions import chronological_partitions


class ChronologicalPartitionTests(unittest.TestCase):
    def test_candle_count_60_20_20_is_chronological_and_nonoverlapping(self) -> None:
        values = candles(100)
        training, validation, locked = chronological_partitions(values, "a" * 64)
        self.assertEqual((training.candle_count, validation.candle_count, locked.candle_count), (60, 20, 20))
        self.assertEqual(training.end, validation.start)
        self.assertEqual(validation.end, locked.start)
        self.assertEqual((training.name, validation.name, locked.name), (
            PartitionName.TRAINING, PartitionName.VALIDATION, PartitionName.LOCKED_TEST,
        ))

    def test_insufficient_and_out_of_order_coverage_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "at least five"):
            chronological_partitions(candles(4), "a" * 64)
        values = list(candles(5))
        values[2], values[3] = values[3], values[2]
        with self.assertRaisesRegex(ValueError, "chronological"):
            chronological_partitions(values, "a" * 64)


if __name__ == "__main__": unittest.main()
