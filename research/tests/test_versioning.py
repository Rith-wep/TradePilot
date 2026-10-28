import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from ingestion_helpers import EURUSD, START, raw_candle
from tradepilot.data.normalization import normalize_provider_candle
from tradepilot.data.storage import ParquetDatasetStore, dataset_identifier


NOW = datetime(2024, 2, 1, tzinfo=timezone.utc)


def canonical(index: int):
    return normalize_provider_candle(
        raw_candle(index), instrument=EURUSD, provider="mock", dataset_version="mock-v1", is_synthetic=True
    )


class VersioningTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.store = ParquetDatasetStore(self.temporary.name)

    def save(self, candles, *, retrieved_at=NOW, metadata=None, allow_revisions=False):
        return self.store.save(
            "mock", EURUSD, "H1", candles,
            retrieved_at=retrieved_at,
            request_start=START,
            request_end=START + timedelta(hours=3),
            provider_metadata=metadata or {},
            allow_revisions=allow_revisions,
        )

    def test_identical_content_reuses_immutable_snapshot(self) -> None:
        first = self.save([canonical(0), canonical(1)])
        original = first.parquet_path.read_bytes()
        second = self.save(
            [canonical(0), canonical(1)],
            retrieved_at=NOW + timedelta(days=1),
            metadata={"retrieval": "second"},
        )
        self.assertEqual(first.dataset_id, second.dataset_id)
        self.assertEqual(first.snapshot_path, second.snapshot_path)
        self.assertEqual(first.parquet_path.read_bytes(), original)
        retrievals = list(first.snapshot_path.parent.parent.joinpath("retrievals").glob("*.json"))
        self.assertEqual(len(retrievals), 2)

    def test_dataset_identifier_ignores_provider_retrieval_metadata(self) -> None:
        candles = [canonical(0), canonical(1)]
        changed_provenance = [
            replace(candle, source="another-provider", dataset_version="another-version")
            for candle in candles
        ]
        self.assertEqual(
            dataset_identifier(candles, EURUSD, "H1"),
            dataset_identifier(changed_provenance, EURUSD, "H1"),
        )

    def test_historical_revision_creates_new_snapshot_and_is_detected(self) -> None:
        first = self.save([canonical(0), canonical(1)])
        old_bytes = first.parquet_path.read_bytes()
        revised = replace(canonical(0), bid_close=Decimal("1.10040"))
        second = self.save([revised], allow_revisions=True)
        self.assertNotEqual(first.dataset_id, second.dataset_id)
        self.assertEqual(len(second.revisions), 1)
        self.assertEqual(first.parquet_path.read_bytes(), old_bytes)
        compared = self.store.compare_snapshots("mock", EURUSD, "H1", first.dataset_id, second.dataset_id)
        self.assertEqual([item.timestamp for item in compared], [START])

    def test_dataset_identifier_is_reproducible_for_input_order(self) -> None:
        candles = [canonical(0), canonical(1)]
        self.assertEqual(
            dataset_identifier(candles, EURUSD, "H1"),
            dataset_identifier(list(reversed(candles)), EURUSD, "H1"),
        )


if __name__ == "__main__":
    unittest.main()

