import tempfile
import unittest

from readiness_helpers import real_candles, stored_integrity
from simulator_helpers import START
from tradepilot.data.readiness_pipeline import verify_candidate_pipeline as legacy_pipeline
from tradepilot.data.sessions import WeeklySessionCalendar
from tradepilot.workflows.real_data_readiness import verify_candidate_pipeline


class ReadinessWorkflowCompatibilityTests(unittest.TestCase):
    def test_legacy_import_reexports_workflow_function(self):
        self.assertIs(legacy_pipeline, verify_candidate_pipeline)
        self.assertEqual(
            legacy_pipeline.__module__,
            "tradepilot.workflows.real_data_readiness",
        )

    def test_legacy_and_workflow_paths_produce_identical_evidence(self):
        with (
            tempfile.TemporaryDirectory() as data,
            tempfile.TemporaryDirectory() as current_reports,
            tempfile.TemporaryDirectory() as legacy_reports,
        ):
            integrity, _ = stored_integrity(data, real_candles())
            calendar = WeeklySessionCalendar(name="workflow-compatibility-test")
            current = verify_candidate_pipeline(
                integrity,
                calendar,
                current_reports,
                implementation_revision="test-revision",
                created_at=START,
            )
            legacy = legacy_pipeline(
                integrity,
                calendar,
                legacy_reports,
                implementation_revision="test-revision",
                created_at=START,
            )

        self.assertEqual(current, legacy)
        self.assertTrue(all(item.reproducible for item in current))


if __name__ == "__main__":
    unittest.main()
