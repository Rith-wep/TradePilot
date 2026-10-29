import hashlib
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from tradepilot.data.dukascopy_csv_cli import main


ROOT = Path(__file__).resolve().parents[1]
BID = ROOT / "fixtures/dukascopy/eurusd_h1_bid.csv"
ASK = ROOT / "fixtures/dukascopy/eurusd_h1_ask.csv"
FORMAT = "%Y-%m-%dT%H:%M:%S%z"


def invoke(arguments):
    stream = io.StringIO()
    with redirect_stdout(stream):
        code = main(arguments)
    return code, json.loads(stream.getvalue())


class DukascopyCsvCliTests(unittest.TestCase):
    def base(self, output, bid=BID, ask=ASK):
        return [
            "--instrument", "EURUSD", "--bid", str(bid), "--ask", str(ask),
            "--timestamp-format", FORMAT, "--output", str(output),
        ]

    def test_success_reports_hashes_quality_and_dataset_identity(self):
        with tempfile.TemporaryDirectory() as output:
            code, result = invoke(self.base(output))
            self.assertEqual(code, 0)
            self.assertTrue(result["success"])
            self.assertEqual(result["bid_sha256"], hashlib.sha256(BID.read_bytes()).hexdigest())
            self.assertEqual(len(result["dataset_id"]), 64)
            self.assertIn("coverage", result)
            self.assertIn("gaps", result)
            self.assertIn("spreads", result)
            self.assertIn("parquet_checksum", result)

    def test_strict_gap_fails_before_snapshot_publication(self):
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            bid = root_path / "bid.csv"
            ask = root_path / "ask.csv"
            bid.write_text("\n".join([BID.read_text().splitlines()[0], BID.read_text().splitlines()[1], BID.read_text().splitlines()[3]]) + "\n")
            ask.write_text("\n".join([ASK.read_text().splitlines()[0], ASK.read_text().splitlines()[1], ASK.read_text().splitlines()[3]]) + "\n")
            output = root_path / "data"
            code, result = invoke(self.base(output, bid, ask) + ["--strict-gaps"])
            self.assertEqual(code, 1)
            self.assertEqual(result["error_code"], "UNEXPECTED_GAPS")
            self.assertFalse(output.exists())

    def test_revisions_fail_then_require_explicit_approval(self):
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            output = root_path / "data"
            first_code, _ = invoke(self.base(output))
            self.assertEqual(first_code, 0)
            bid = root_path / "bid.csv"
            ask = root_path / "ask.csv"
            bid.write_text(BID.read_text().replace("1.10050,100", "1.10055,100", 1))
            ask.write_text(ASK.read_text().replace("1.10070,90", "1.10075,90", 1))
            rejected_code, rejected = invoke(self.base(output, bid, ask))
            self.assertEqual(rejected_code, 1)
            self.assertEqual(rejected["error_code"], "UNAPPROVED_REVISIONS")
            approved_code, approved = invoke(self.base(output, bid, ask) + ["--approve-revisions"])
            self.assertEqual(approved_code, 0)
            self.assertEqual(approved["revision_count"], 1)
            self.assertTrue(approved["revisions_approved"])


if __name__ == "__main__": unittest.main()
