import json
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from ingestion_helpers import EURUSD, START, raw_candle
from tradepilot.data.integrity import verify_dataset
from tradepilot.data.normalization import normalize_provider_candle
from tradepilot.data.storage import ParquetDatasetStore


NOW = datetime(2024, 2, 1, tzinfo=timezone.utc)


def canonical(index: int):
    return normalize_provider_candle(
        raw_candle(index), instrument=EURUSD, provider="mock", dataset_version="v1", is_synthetic=True
    )


class IntegrityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.store = ParquetDatasetStore(self.temporary.name)
        self.stored = self.store.save(
            "mock", EURUSD, "H1", [canonical(0), canonical(1)],
            retrieved_at=NOW,
            request_start=START,
            request_end=START + timedelta(hours=2),
        )
        self.dataset_root = self.store.dataset_directory("mock", EURUSD, "H1")

    def test_valid_snapshot_verifies_all_checksums(self) -> None:
        report = verify_dataset(self.dataset_root)
        self.assertTrue(report.valid)
        self.assertEqual(report.dataset_id, self.stored.dataset_id)
        self.assertEqual(report.row_count, 2)
        self.assertEqual(report.retrieval_count, 1)

    def test_corrupted_parquet_is_detected(self) -> None:
        payload = bytearray(self.stored.parquet_path.read_bytes())
        payload[len(payload) // 2] ^= 0xFF
        self.stored.parquet_path.write_bytes(payload)
        report = verify_dataset(self.dataset_root)
        codes = {issue.code for issue in report.issues}
        self.assertFalse(report.valid)
        self.assertIn("parquet_checksum_mismatch", codes)

    def test_manifest_checksum_mismatch_is_detected(self) -> None:
        manifest = json.loads(self.stored.manifest_path.read_text(encoding="utf-8"))
        manifest["dataset_sha256"] = "0" * 64
        self.stored.manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        report = verify_dataset(self.dataset_root)
        self.assertFalse(report.valid)
        self.assertIn("dataset_checksum_mismatch", {issue.code for issue in report.issues})

    def test_missing_parquet_file_is_detected(self) -> None:
        self.stored.parquet_path.unlink()
        report = verify_dataset(self.dataset_root)
        self.assertFalse(report.valid)
        self.assertIn("missing_parquet", {issue.code for issue in report.issues})

    def test_index_manifest_mismatch_is_detected(self) -> None:
        index_path = self.dataset_root / "index.json"
        index = json.loads(index_path.read_text(encoding="utf-8"))
        index["instrument"] = "GBPUSD"
        index_path.write_text(json.dumps(index), encoding="utf-8")
        report = verify_dataset(self.dataset_root)
        self.assertFalse(report.valid)
        self.assertIn("index_instrument_mismatch", {issue.code for issue in report.issues})

    def test_decimal_scale_round_trip_preserves_content_identity(self) -> None:
        separate = tempfile.TemporaryDirectory()
        self.addCleanup(separate.cleanup)
        store = ParquetDatasetStore(separate.name)
        scaled = replace(canonical(0), bid_high=Decimal("2.5"), ask_high=Decimal("2.5"))
        stored = store.save(
            "mock", EURUSD, "H1", [scaled], retrieved_at=NOW,
            request_start=START, request_end=START + timedelta(hours=1),
        )
        self.assertTrue(verify_dataset(stored.snapshot_path).valid)


if __name__ == "__main__":
    unittest.main()

