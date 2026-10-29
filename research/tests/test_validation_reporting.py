import unittest
from decimal import Decimal

from tradepilot.validation.models import BootstrapInterval, UncertaintyStatus, ValidationContent, VALIDATION_MODEL_VERSION
from tradepilot.validation.parameters import select_configuration
from tradepilot.validation.reporting import build_validation_report
from tradepilot.validation.robustness import summarize_robustness
from validation_helpers import evaluation


class ValidationReportingTests(unittest.TestCase):
    def test_zero_and_insufficient_folds_are_not_silently_dropped(self) -> None:
        normal = evaluation(expectancy="1", trades=30)
        zero = evaluation("b" * 64, expectancy=None, trades=0)
        summary = summarize_robustness((normal, zero))
        self.assertEqual(summary.fold_count, 2)
        self.assertEqual(summary.insufficient_folds, 1)
        self.assertEqual(summary.fraction_positive.value, 0.5)

    def test_identical_content_has_identical_report_identity(self) -> None:
        item = evaluation()
        robustness = summarize_robustness((item,))
        content = ValidationContent(
            VALIDATION_MODEL_VERSION, "a" * 64, "b" * 64, "strategy", "1.0.0", "revision",
            (), (), (item.configuration,), (item,), select_configuration((item,)),
            None, None, robustness,
            BootstrapInterval(UncertaintyStatus.DEFINED, Decimal("-1"), Decimal("2"), 30, 5, 1000),
            ("SYNTHETIC_DATA_ONLY",),
        )
        first = build_validation_report(content)
        second = build_validation_report(content)
        self.assertEqual(first.report_id, second.report_id)
        self.assertEqual(len(first.report_id), 64)


if __name__ == "__main__": unittest.main()
