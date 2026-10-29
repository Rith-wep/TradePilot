import unittest

from simulator_helpers import setup
from validation_helpers import candles
from tradepilot.validation.partitions import chronological_partitions
from tradepilot.validation.warmup import eligible_setups, historical_prefix


class ValidationWarmupTests(unittest.TestCase):
    def test_full_prefix_warmup_does_not_admit_earlier_signals(self) -> None:
        values = candles(10)
        training, validation, _ = chronological_partitions(values, "a" * 64)
        self.assertEqual(len(historical_prefix(values, validation)), validation.end_index)
        selected = eligible_setups((setup(0), setup(validation.start_index)), validation)
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0].detection_candle_open_time, values[validation.start_index].timestamp)

    def test_final_detection_observable_at_next_boundary_is_excluded(self) -> None:
        values = candles(10)
        training, validation, _ = chronological_partitions(values, "a" * 64)
        final_training = setup(training.end_index - 1)
        self.assertEqual(final_training.observable_at, training.end)
        self.assertEqual(eligible_setups((final_training,), training), ())
        self.assertEqual(eligible_setups((final_training,), validation), ())


if __name__ == "__main__": unittest.main()
