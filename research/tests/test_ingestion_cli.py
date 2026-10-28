import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from tradepilot.data.ingestion_cli import main


ROOT = Path(__file__).resolve().parents[1]


class IngestionCliTests(unittest.TestCase):
    def test_mock_cli_writes_dataset(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                exit_code = main([
                    "--input", str(ROOT / "fixtures/synthetic_eurusd_h1.csv"),
                    "--output", directory,
                ])
            result = json.loads(output.getvalue())
            self.assertEqual(exit_code, 0)
            self.assertTrue(result["success"])
            self.assertEqual(result["row_count"], 5)
            self.assertTrue(Path(result["parquet_path"]).exists())


if __name__ == "__main__":
    unittest.main()
