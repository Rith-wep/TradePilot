import json
import tempfile
import unittest
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from reporting_helpers import CREATED_AT, build_run, create_context
from tradepilot.reporting.canonical import canonical_json_bytes
from tradepilot.reporting.storage import report_identifier
from tradepilot.reporting.validation import ReportValidationError, build_research_run, resolve_implementation_revision
from tradepilot.strategies.base import configuration_fingerprint
from tradepilot.strategies.breakout import BreakoutConfig


class ResearchReportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        context = create_context(self.temporary.name)
        self.root, self.integrity, self.calendar, self.config, self.strategy, self.fingerprint, self.setups = context

    def make_run(self, **changes):
        values = {
            "integrity": self.integrity,
            "calendar": self.calendar,
            "config": self.config,
            "strategy": self.strategy,
            "fingerprint": self.fingerprint,
            "setups": self.setups,
        }
        values.update(changes)
        return build_run(**values)

    def test_identical_content_has_same_id_despite_creation_time(self) -> None:
        first = self.make_run(created_at=CREATED_AT)
        second = self.make_run(created_at=CREATED_AT + timedelta(days=1))
        self.assertEqual(report_identifier(first.content), report_identifier(second.content))

    def test_configuration_change_changes_report_identity(self) -> None:
        first = self.make_run()
        changed = BreakoutConfig(lookback=3)
        fingerprint = configuration_fingerprint(
            self.strategy.name, self.strategy.version, changed, self.calendar.calendar_id
        )
        changed_setups = tuple(replace(setup, configuration_fingerprint=fingerprint) for setup in self.setups)
        second = self.make_run(config=changed, fingerprint=fingerprint, setups=changed_setups)
        self.assertNotEqual(report_identifier(first.content), report_identifier(second.content))

    def test_changed_dataset_snapshot_changes_report_identity(self) -> None:
        separate = tempfile.TemporaryDirectory()
        self.addCleanup(separate.cleanup)
        _, integrity, calendar, config, strategy, fingerprint, setups = create_context(separate.name, extra_candle=True)
        first = self.make_run()
        second = build_run(integrity, calendar, config, strategy, fingerprint, setups)
        self.assertNotEqual(report_identifier(first.content), report_identifier(second.content))

    def test_decimal_serialization_is_exact_string(self) -> None:
        precise = Decimal("1.1234567890123456789012345678901234")
        setup = replace(self.setups[0], structural_invalidation_reference=precise)
        run = self.make_run(setups=(setup,))
        document = json.loads(canonical_json_bytes(run.content))
        stored = document["signals"][0]["setup"]["structural_invalidation_reference"]
        self.assertEqual(stored, "1.1234567890123456789012345678901234")

    def test_invalid_h1_observable_timestamp_is_rejected(self) -> None:
        invalid = replace(self.setups[0], observable_at=self.setups[0].observable_at + timedelta(minutes=1))
        with self.assertRaisesRegex(ReportValidationError, "observable timestamp"):
            self.make_run(setups=(invalid,))

    def test_detection_timestamp_must_exist_in_dataset(self) -> None:
        absent = self.setups[0].detection_candle_open_time - timedelta(minutes=30)
        invalid = replace(
            self.setups[0], detection_candle_open_time=absent, observable_at=absent + timedelta(hours=1)
        )
        with self.assertRaisesRegex(ReportValidationError, "absent from selected dataset"):
            self.make_run(setups=(invalid,))

    def test_duplicate_setup_records_are_rejected(self) -> None:
        with self.assertRaisesRegex(ReportValidationError, "duplicate setup"):
            self.make_run(setups=(self.setups[0], self.setups[0]))

    def test_zero_candidate_report_is_valid(self) -> None:
        run = self.make_run(setups=())
        self.assertEqual(run.content.signals, ())

    def test_implementation_revision_changes_identity_and_is_preserved(self) -> None:
        first = self.make_run(revision="revision-a")
        second = self.make_run(revision="revision-b")
        self.assertEqual(first.content.implementation_revision, "revision-a")
        self.assertNotEqual(report_identifier(first.content), report_identifier(second.content))

    def test_implementation_revision_falls_back_when_git_is_unavailable(self) -> None:
        with patch.dict("os.environ", {}, clear=True), patch(
            "tradepilot.reporting.validation.subprocess.run", side_effect=FileNotFoundError
        ):
            self.assertEqual(resolve_implementation_revision(), "unknown")


if __name__ == "__main__":
    unittest.main()

