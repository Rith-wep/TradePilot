import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path

from reporting_helpers import CREATED_AT, build_run, create_context
from tradepilot.reporting.canonical import canonical_json_bytes
from tradepilot.reporting.storage import ReportStorage, ReportStorageError, report_identifier, verify_report


class ReportStorageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.datasets = tempfile.TemporaryDirectory()
        self.reports = tempfile.TemporaryDirectory()
        self.addCleanup(self.datasets.cleanup)
        self.addCleanup(self.reports.cleanup)
        _, integrity, calendar, config, strategy, fingerprint, setups = create_context(self.datasets.name)
        self.run = build_run(integrity, calendar, config, strategy, fingerprint, setups)
        self.storage = ReportStorage(self.reports.name)

    def test_valid_existing_report_is_reused(self) -> None:
        first = self.storage.save(self.run)
        second = self.storage.save(self.run)
        self.assertFalse(first.reused)
        self.assertTrue(second.reused)
        self.assertEqual(first.report_id, second.report_id)
        self.assertTrue(verify_report(first.report_path.parent).valid)

    def test_concurrent_identical_writers_publish_one_valid_report(self) -> None:
        with ThreadPoolExecutor(max_workers=6) as executor:
            results = list(executor.map(lambda _: self.storage.save(self.run), range(12)))
        self.assertEqual(len({result.report_id for result in results}), 1)
        report_id = results[0].report_id
        self.assertTrue(verify_report(self.storage.root / report_id).valid)
        published = [path for path in self.storage.root.iterdir() if not path.name.startswith(".staging-")]
        self.assertEqual([path.name for path in published], [report_id])

    def test_incomplete_existing_publication_is_rejected(self) -> None:
        report_id = report_identifier(self.run.content)
        incomplete = self.storage.root / report_id
        incomplete.mkdir(parents=True)
        with self.assertRaisesRegex(ReportStorageError, "corrupt or conflicting"):
            self.storage.save(self.run)

    def test_corrupted_existing_report_is_rejected(self) -> None:
        stored = self.storage.save(self.run)
        stored.report_path.write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(ReportStorageError, "corrupt or conflicting"):
            self.storage.save(self.run)

    def test_repeated_runs_record_metadata_without_changing_report(self) -> None:
        first = self.storage.save(self.run)
        later = type(self.run)(self.run.content, CREATED_AT + timedelta(days=1))
        second = self.storage.save(later)
        self.assertEqual(first.report_id, second.report_id)
        run_files = list(first.report_path.parent.joinpath("runs").glob("*.json"))
        self.assertEqual(len(run_files), 2)
        created = {json.loads(path.read_text(encoding="utf-8"))["created_at"] for path in run_files}
        self.assertEqual(created, {"2024-03-01T00:00:00Z", "2024-03-02T00:00:00Z"})

    def test_publication_uses_short_private_staging_path(self) -> None:
        nested = Path(self.reports.name) / ("long-report-root-" + "x" * 48)
        stored = ReportStorage(nested).save(self.run)
        self.assertTrue(verify_report(stored.report_path.parent).valid)


if __name__ == "__main__":
    unittest.main()

