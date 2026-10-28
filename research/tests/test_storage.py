import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ingestion_helpers import EURUSD, START, raw_candle
from tradepilot.data.normalization import normalize_provider_candle
from tradepilot.data.storage import ParquetDatasetStore, StorageError


NOW = datetime(2024, 2, 1, tzinfo=timezone.utc)


def canonical(index: int):
    return normalize_provider_candle(
        raw_candle(index),
        instrument=EURUSD,
        provider="mock",
        dataset_version="mock-v1",
        is_synthetic=True,
    )


class StorageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.store = ParquetDatasetStore(self.temporary.name)

    def save(self, candles):
        return self.store.save(
            "mock", EURUSD, "H1", candles,
            retrieved_at=NOW,
            request_start=START,
            request_end=START + timedelta(hours=3),
            provider_metadata={"test": "true"},
        )

    def test_writes_real_parquet_and_checksum_manifest(self) -> None:
        stored = self.save([canonical(0), canonical(1)])
        self.assertEqual(stored.parquet_path.read_bytes()[:4], b"PAR1")
        manifest = json.loads(stored.manifest_path.read_text(encoding="utf-8"))
        actual = hashlib.sha256(stored.parquet_path.read_bytes()).hexdigest()
        self.assertEqual(manifest["parquet_sha256"], actual)
        self.assertEqual(manifest["price_basis"], "bid_ask")
        self.assertEqual(manifest["row_count"], 2)

    def test_repeated_save_is_idempotent(self) -> None:
        first = self.save([canonical(0), canonical(1)])
        second = self.save([canonical(0), canonical(1)])
        self.assertEqual(first.dataset_checksum, second.dataset_checksum)
        self.assertEqual(second.row_count, 2)
        self.assertEqual(len(self.store.load("mock", EURUSD, "H1")), 2)

    def test_incremental_save_merges_without_duplicates(self) -> None:
        self.save([canonical(0), canonical(1)])
        stored = self.save([canonical(1), canonical(2)])
        self.assertEqual(stored.row_count, 3)

    def test_conflicting_existing_candle_is_rejected(self) -> None:
        self.save([canonical(0)])
        conflicting = normalize_provider_candle(
            raw_candle(0, bid_close="1.10040"),
            instrument=EURUSD, provider="mock", dataset_version="mock-v1", is_synthetic=True,
        )
        with self.assertRaisesRegex(StorageError, "conflicting candle"):
            self.save([conflicting])


if __name__ == "__main__":
    unittest.main()

