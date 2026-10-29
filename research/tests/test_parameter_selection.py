import unittest

from validation_helpers import evaluation
from tradepilot.validation.parameters import approved_parameter_grid, select_configuration


class ParameterSelectionTests(unittest.TestCase):
    def test_approved_grid_uses_existing_configurable_fields(self) -> None:
        grid = approved_parameter_grid("calendar")
        self.assertEqual(len(grid), 5)
        self.assertEqual([getattr(config, "lookback") for config, _ in grid[:3]], [10, 20, 40])
        self.assertEqual([getattr(config, "ema_period") for config, _ in grid[3:]], [100, 200])

    def test_selection_enforces_samples_and_retains_rejections(self) -> None:
        best = evaluation("a" * 64, "2", 30)
        lower = evaluation("b" * 64, "1", 30)
        rejected = evaluation("c" * 64, "9", 2)
        decision = select_configuration((lower, rejected, best), minimum_trades=30)
        self.assertEqual(decision.selected_configuration_fingerprint, "a" * 64)
        self.assertIn(("c" * 64, "INSUFFICIENT_TRADES"), decision.rejected)


if __name__ == "__main__": unittest.main()
