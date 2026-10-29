import tempfile
import unittest
from dataclasses import replace
from datetime import timedelta

from ingestion_helpers import EURUSD, START, raw_candle
from tradepilot.data.ingestion import HistoricalIngestor
from tradepilot.data.providers.mock import MockMarketDataProvider
from tradepilot.data.storage import ParquetDatasetStore, StorageError


class ReadinessRevisionTests(unittest.TestCase):
    def test_revision_requires_approval_and_preserves_previous_snapshot(self):
        with tempfile.TemporaryDirectory() as root:
            store = ParquetDatasetStore(root)
            first = HistoricalIngestor(
                MockMarketDataProvider((raw_candle(0),), name="oanda-v20"), store,
            ).ingest(EURUSD, "H1", START, START + timedelta(hours=1))
            changed = replace(raw_candle(0), bid_close="1.10040")
            with self.assertRaisesRegex(StorageError, "conflicting candle"):
                HistoricalIngestor(
                    MockMarketDataProvider((changed,), name="oanda-v20"), store,
                ).ingest(EURUSD, "H1", START, START + timedelta(hours=1))
            self.assertEqual(store.latest_dataset_id("oanda-v20", EURUSD, "H1"), first.stored.dataset_id)
            approved = HistoricalIngestor(
                MockMarketDataProvider((changed,), name="oanda-v20"), store,
            ).ingest(
                EURUSD, "H1", START, START + timedelta(hours=1), allow_revisions=True,
            )
            self.assertNotEqual(approved.stored.dataset_id, first.stored.dataset_id)
            self.assertEqual(len(approved.stored.revisions), 1)
            self.assertTrue(first.stored.snapshot_path.exists())


if __name__ == "__main__": unittest.main()
