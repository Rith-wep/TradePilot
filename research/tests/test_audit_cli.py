import contextlib
import io
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from ingestion_helpers import EURUSD, START, raw_candle
from tradepilot.data.audit_cli import main
from tradepilot.data.normalization import normalize_provider_candle
from tradepilot.data.storage import ParquetDatasetStore


class AuditCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.store = ParquetDatasetStore(self.temporary.name)
        candles = [
            normalize_provider_candle(
                raw_candle(index), instrument=EURUSD, provider="mock", dataset_version="v1", is_synthetic=True
            )
            for index in (0, 2)
        ]
        self.stored = self.store.save(
            "mock", EURUSD, "H1", candles,
            retrieved_at=datetime(2024, 2, 1, tzinfo=timezone.utc),
            request_start=START,
            request_end=START + timedelta(hours=3),
        )
        self.root = self.store.dataset_directory("mock", EURUSD, "H1")

    def test_audit_reports_identity_quality_and_gaps(self) -> None:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            exit_code = main([str(self.root)])
        result = json.loads(output.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertTrue(result["valid"])
        self.assertEqual(result["provider"], "mock")
        self.assertEqual(result["row_count"], 2)
        self.assertEqual(result["gaps"]["unexpected_missing_count"], 1)

    def test_audit_returns_nonzero_for_integrity_failure(self) -> None:
        self.stored.parquet_path.write_bytes(b"corrupt")
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            exit_code = main([str(self.root)])
        self.assertEqual(exit_code, 1)
        self.assertFalse(json.loads(output.getvalue())["valid"])


if __name__ == "__main__":
    unittest.main()
