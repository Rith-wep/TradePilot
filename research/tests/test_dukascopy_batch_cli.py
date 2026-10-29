import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from batch_helpers import create_batch_plan
from tradepilot.data.dukascopy_batch_cli import main
from tradepilot.validation.partition_governance import verify_sealed_partitions


class DukascopyBatchCliTests(unittest.TestCase):
    def test_cli_publishes_snapshot_and_sealed_unevaluated_partitions(self):
        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            output = StringIO()
            with redirect_stdout(output):
                code = main([str(create_batch_plan(base)), "--output", str(base / "data")])
            payload = json.loads(output.getvalue())

            self.assertEqual(code, 0)
            self.assertTrue(payload["success"])
            self.assertEqual(payload["row_count"], 48)
            self.assertEqual(payload["locked_test_state"], "SEALED")
            self.assertFalse(payload["locked_test_evaluated"])
            governance = (
                base / "data" / "dukascopy-csv-batch" / "EURUSD" / "H1"
                / "governance" / payload["dataset_id"] / "sealed-partitions.json"
            )
            self.assertTrue(verify_sealed_partitions(governance))

    def test_cli_fails_closed_without_publishing_on_invalid_hash(self):
        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            output = StringIO()
            with redirect_stdout(output):
                code = main([
                    str(create_batch_plan(base, bad_hash=True)),
                    "--output", str(base / "data"),
                ])
            payload = json.loads(output.getvalue())
            self.assertEqual(code, 1)
            self.assertFalse(payload["success"])
            self.assertFalse((base / "data" / "dukascopy-csv-batch").exists())


if __name__ == "__main__":
    unittest.main()
