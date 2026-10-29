import unittest
from dataclasses import replace

from tradepilot.validation.engine import configuration_evaluation
from tradepilot.validation.models import EvaluationStatus
from validation_helpers import declaration, scenario


class ValidationEngineTests(unittest.TestCase):
    def test_zero_trade_result_is_retained_and_labelled(self):
        result = configuration_evaluation(
            declaration(), "p" * 64, (scenario(trades=0, expectancy=None),), minimum_trades=10,
        )
        self.assertEqual(result.status, EvaluationStatus.ZERO_TRADES)
        self.assertEqual(len(result.scenarios), 1)
        self.assertIn("ZERO_TRADES_RETAINED", result.warnings)

    def test_forced_and_ambiguous_exits_are_disclosed(self):
        item = replace(scenario(trades=10, expectancy="1"), forced_exits=1, ambiguous_exits=1)
        result = configuration_evaluation(declaration(), "p" * 64, (item,), minimum_trades=10)
        self.assertEqual(result.status, EvaluationStatus.ELIGIBLE)
        self.assertIn("FORCED_TERMINAL_EXITS_INCLUDED", result.warnings)
        self.assertIn("AMBIGUOUS_EXITS_INCLUDED", result.warnings)


if __name__ == "__main__": unittest.main()
