import json
import tempfile
import unittest
from datetime import time, timedelta
from pathlib import Path

from readiness_helpers import real_candles, stored_integrity
from simulator_helpers import START
from tradepilot.data.readiness import ReadinessPolicy, build_readiness_report
from tradepilot.data.readiness_storage import ReadinessReportStore, ReadinessStorageError, verify_readiness_report
from tradepilot.data.sessions import WeeklySessionCalendar


class ReadinessStorageTests(unittest.TestCase):
    def test_identical_report_reuses_and_corruption_fails(self):
        with tempfile.TemporaryDirectory() as data, tempfile.TemporaryDirectory() as reports:
            integrity, _ = stored_integrity(data, real_candles())
            report = build_readiness_report(
                integrity, requested_start=START, requested_end=START + timedelta(hours=240),
                calendar=WeeklySessionCalendar(name="storage-test"),
                policy=ReadinessPolicy(minimum_candles=1),
            )
            store = ReadinessReportStore(reports)
            first = store.save(report)
            second = store.save(report)
            self.assertFalse(first.reused)
            self.assertTrue(second.reused)
            self.assertTrue(verify_readiness_report(first.path))
            first.path.write_text("{}", encoding="utf-8")
            self.assertFalse(verify_readiness_report(first.path))
            with self.assertRaisesRegex(ReadinessStorageError, "corrupted|conflicts"):
                store.save(report)


if __name__ == "__main__": unittest.main()
