import contextlib
import io
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from ingestion_helpers import EURUSD
from strategy_helpers import strategy_candle
from tradepilot.data.storage import ParquetDatasetStore
from tradepilot.strategies.cli import main


class StrategyCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        store = ParquetDatasetStore(self.temporary.name)
        candles = [
            strategy_candle(0, "9", high="10", low="8"),
            strategy_candle(1, "10", high="11", low="9"),
            strategy_candle(2, "12", high="12.5", low="10"),
        ]
        self.stored = store.save(
            "mock", EURUSD, "H1", candles,
            retrieved_at=datetime(2024, 2, 1, tzinfo=timezone.utc),
            request_start=candles[0].timestamp,
            request_end=candles[-1].timestamp + timedelta(hours=1),
        )
        self.root = store.dataset_directory("mock", EURUSD, "H1")

    def test_cli_reports_candidate_without_performance_metrics(self) -> None:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            exit_code = main([str(self.root), "breakout", "--lookback", "2"])
        result = json.loads(output.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(result["dataset_id"], self.stored.dataset_id)
        self.assertEqual(result["candidate_count"], 1)
        self.assertEqual(result["setups"][0]["direction"], "LONG")
        self.assertEqual(result["setups"][0]["detection_candle_open_time"], "2024-01-01T02:00:00Z")
        self.assertEqual(result["setups"][0]["observable_at"], "2024-01-01T03:00:00Z")
        self.assertNotIn("profit", json.dumps(result).lower())

    def test_cli_refuses_corrupt_dataset(self) -> None:
        self.stored.parquet_path.write_bytes(b"corrupt")
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            exit_code = main([str(self.root), "breakout", "--lookback", "2"])
        self.assertEqual(exit_code, 1)
        self.assertIn("integrity verification failed", json.loads(output.getvalue())["error"])


if __name__ == "__main__":
    unittest.main()
