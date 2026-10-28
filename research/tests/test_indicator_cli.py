import contextlib
import io
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from ingestion_helpers import EURUSD, START, raw_candle
from tradepilot.data.normalization import normalize_provider_candle
from tradepilot.data.storage import ParquetDatasetStore
from tradepilot.indicators.cli import main


class IndicatorCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        store = ParquetDatasetStore(self.temporary.name)
        candles = [
            normalize_provider_candle(
                raw_candle(index), instrument=EURUSD, provider="mock", dataset_version="v1", is_synthetic=True
            )
            for index in range(5)
        ]
        self.stored = store.save(
            "mock", EURUSD, "H1", candles,
            retrieved_at=datetime(2024, 2, 1, tzinfo=timezone.utc),
            request_start=START,
            request_end=START + timedelta(hours=5),
        )
        self.root = store.dataset_directory("mock", EURUSD, "H1")

    def test_cli_loads_verified_snapshot_and_calculates_indicators(self) -> None:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            exit_code = main([str(self.root), "--ema-period", "3", "--rsi-period", "3", "--atr-period", "3"])
        result = json.loads(output.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(result["dataset_id"], self.stored.dataset_id)
        self.assertEqual(result["completed_candle_count"], 5)
        self.assertEqual([item["name"] for item in result["indicators"]], ["EMA", "RSI", "ATR"])

    def test_cli_refuses_corrupt_snapshot(self) -> None:
        self.stored.parquet_path.write_bytes(b"corrupt")
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            exit_code = main([str(self.root)])
        self.assertEqual(exit_code, 1)
        self.assertIn("integrity verification failed", json.loads(output.getvalue())["error"])


if __name__ == "__main__":
    unittest.main()
