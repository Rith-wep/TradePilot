import json
import tempfile
import unittest
from pathlib import Path

from batch_helpers import create_batch_plan
from tradepilot.data.dukascopy_batch import DukascopyBatchError, import_batch, load_batch_plan
from tradepilot.data.integrity import verify_dataset
from tradepilot.data.storage import ParquetDatasetStore, StorageError


class DukascopyBatchTests(unittest.TestCase):
    def test_eurusd_and_gbpusd_publish_separate_verified_snapshots(self):
        for symbol in ("EURUSD", "GBPUSD"):
            with self.subTest(symbol=symbol), tempfile.TemporaryDirectory() as root:
                base = Path(root)
                result = import_batch(create_batch_plan(base, instrument=symbol), ParquetDatasetStore(base / "data"))
                self.assertTrue(result.integrity.valid)
                self.assertEqual(result.integrity.instrument, symbol)
                self.assertEqual(result.stored.row_count, 48)
                self.assertEqual(len(result.artifacts.artifacts), 4)
                self.assertTrue(result.stored.source_artifacts_path.exists())
                self.assertTrue(all(item.coverage_ratio == 1 for item in result.quality.monthly))
                self.assertTrue(all(item.coverage_ratio == 1 for item in result.quality.yearly))

    def test_hash_gap_and_missing_month_fail_before_publication(self):
        for mode in ("hash", "gap", "month"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as root:
                base = Path(root)
                plan = create_batch_plan(base, bad_hash=mode == "hash", gap=mode == "gap")
                if mode == "month":
                    payload = json.loads(plan.read_text())
                    payload["months"][1]["month"] = "2024-03"
                    plan.write_text(json.dumps(payload))
                with self.assertRaises(DukascopyBatchError):
                    import_batch(plan, ParquetDatasetStore(base / "data"))
                self.assertFalse((base / "data/dukascopy-csv-batch").exists())

    def test_repeated_batch_is_deterministic_and_revision_requires_approval(self):
        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            store = ParquetDatasetStore(base / "data")
            plan = create_batch_plan(base)
            first = import_batch(plan, store)
            repeated = import_batch(plan, store)
            self.assertEqual(first.stored.dataset_id, repeated.stored.dataset_id)
            self.assertEqual(len(repeated.stored.revisions), 0)
            revised_plan = create_batch_plan(base, changed=True)
            with self.assertRaisesRegex(StorageError, "conflicting candle"):
                import_batch(revised_plan, store)
            revised = import_batch(revised_plan, store, allow_revisions=True)
            self.assertNotEqual(first.stored.dataset_id, revised.stored.dataset_id)
            self.assertEqual(len(revised.stored.revisions), 1)
            self.assertTrue(first.stored.snapshot_path.exists())

    def test_source_artifact_corruption_is_detected_without_breaking_legacy(self):
        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            result = import_batch(create_batch_plan(base), ParquetDatasetStore(base / "data"))
            result.stored.source_artifacts_path.write_bytes(b"{}")
            report = verify_dataset(result.stored.snapshot_path)
            self.assertFalse(report.valid)
            self.assertIn("source_artifacts_checksum_mismatch", {item.code for item in report.issues})


if __name__ == "__main__": unittest.main()
