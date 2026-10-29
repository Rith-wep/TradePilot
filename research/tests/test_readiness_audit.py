import tempfile
import unittest
from dataclasses import replace
from datetime import time, timedelta
from decimal import Decimal

from readiness_helpers import real_candles, stored_integrity
from simulator_helpers import START
from tradepilot.data.readiness import ReadinessPolicy, ReadinessStatus, build_readiness_report
from tradepilot.data.sessions import WeeklySessionCalendar
from tradepilot.data.storage import CandleRevision


CALENDAR = WeeklySessionCalendar("UTC", 6, time(22), 4, time(22), name="test-fx")


class ReadinessAuditTests(unittest.TestCase):
    def integrity(self, values):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        return stored_integrity(temporary.name, values)[0]

    def test_complete_real_snapshot_is_ready_and_deterministic(self):
        integrity = self.integrity(real_candles())
        kwargs = dict(
            requested_start=START, requested_end=START + timedelta(hours=240),
            calendar=CALENDAR, policy=ReadinessPolicy(minimum_candles=200),
        )
        first = build_readiness_report(integrity, **kwargs)
        second = build_readiness_report(integrity, **kwargs)
        self.assertEqual(first.content.status, ReadinessStatus.READY)
        self.assertEqual(first.report_id, second.report_id)
        self.assertEqual(first.content.coverage.coverage_ratio, Decimal("1"))

    def test_missing_open_candle_fails_coverage_and_gap_policy(self):
        integrity = self.integrity(real_candles(missing=(5,)))
        report = build_readiness_report(
            integrity, requested_start=START, requested_end=START + timedelta(hours=240),
            calendar=CALENDAR,
            policy=ReadinessPolicy(minimum_candles=1, minimum_coverage=Decimal("1")),
        )
        codes = {item.code for item in report.content.issues}
        self.assertEqual(report.content.status, ReadinessStatus.FAILED)
        self.assertIn("INSUFFICIENT_COVERAGE", codes)
        self.assertIn("UNEXPECTED_GAPS", codes)

    def test_non_oanda_data_fails_closed(self):
        integrity = replace(self.integrity(real_candles()), provider="mock")
        report = build_readiness_report(
            integrity, requested_start=START, requested_end=START + timedelta(hours=240),
            calendar=CALENDAR, policy=ReadinessPolicy(minimum_candles=1),
        )
        self.assertIn("INCOMPATIBLE_PROVIDER", {item.code for item in report.content.issues})

    def test_revisions_require_explicit_approval(self):
        integrity = self.integrity(real_candles())
        revision = CandleRevision(START, "a" * 64, "b" * 64)
        common = dict(
            requested_start=START, requested_end=START + timedelta(hours=240),
            calendar=CALENDAR, policy=ReadinessPolicy(minimum_candles=1),
            previous_dataset_id="c" * 64, revisions=(revision,),
        )
        rejected = build_readiness_report(integrity, **common)
        approved = build_readiness_report(integrity, revisions_approved=True, **common)
        self.assertIn("UNAPPROVED_REVISIONS", {item.code for item in rejected.content.issues})
        self.assertEqual(approved.content.status, ReadinessStatus.READY)


if __name__ == "__main__": unittest.main()
