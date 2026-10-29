import tempfile
import unittest
from datetime import time

from readiness_helpers import real_candles, stored_integrity
from simulator_helpers import START
from tradepilot.data.sessions import WeeklySessionCalendar
from tradepilot.workflows.real_data_readiness import verify_candidate_pipeline


class ReadinessPipelineTests(unittest.TestCase):
    def test_zero_signal_reports_are_valid_and_reproducible(self):
        with tempfile.TemporaryDirectory() as data, tempfile.TemporaryDirectory() as reports:
            integrity, _ = stored_integrity(data, real_candles())
            evidence = verify_candidate_pipeline(
                integrity, WeeklySessionCalendar(name="pipeline-test"), reports,
                implementation_revision="test-revision", created_at=START,
            )
            self.assertEqual(len(evidence), 2)
            self.assertTrue(all(item.reproducible for item in evidence))
            self.assertTrue(all(item.candidate_report_id == item.repeated_report_id for item in evidence))
            self.assertTrue(all(item.signal_count == 0 for item in evidence))


if __name__ == "__main__": unittest.main()
