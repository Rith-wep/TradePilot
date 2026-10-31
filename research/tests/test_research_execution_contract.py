import json
import tempfile
import unittest
from pathlib import Path

from reporting_helpers import create_context
from tradepilot.execution.contract import CONTRACT_VERSION, execute
from tradepilot.reporting.storage import verify_report
from tradepilot.reporting.validation import resolve_implementation_revision


class ResearchExecutionContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.data = self.root / "data"
        self.reports = self.root / "reports"
        self.reports.mkdir()
        _, integrity, *_ = create_context(str(self.data))
        self.dataset_id = integrity.dataset_id

    def tearDown(self) -> None:
        self.temp.cleanup()

    def request(self, strategy: str) -> bytes:
        return json.dumps({
            "contract_version": CONTRACT_VERSION, "request_id": "contract-test",
            "dataset_id": self.dataset_id, "instrument": "EURUSD",
            "timeframe": "H1", "strategy": strategy,
            "implementation_revision": resolve_implementation_revision(Path.cwd()),
        }).encode()

    def test_breakout_and_pullback_publish_verified_reproducible_reports(self) -> None:
        for strategy in ("price_range_breakout", "ema_rsi_trend_pullback"):
            first, code = execute(self.request(strategy), self.data, self.reports, Path.cwd())
            second, repeated_code = execute(self.request(strategy), self.data, self.reports, Path.cwd())
            self.assertEqual((code, repeated_code), (0, 0))
            self.assertEqual(first["report_id"], second["report_id"])
            self.assertTrue(second["reused"])
            self.assertTrue(verify_report(self.reports / str(first["report_id"])).valid)
        self.assertEqual(first["signal_count"], 0)

    def test_invalid_missing_and_genuinely_corrupted_datasets_fail_closed(self) -> None:
        invalid, code = execute(b"{}", self.data, self.reports, Path.cwd())
        self.assertEqual(code, 2)
        self.assertEqual(invalid["status"], "ERROR")
        missing = json.loads(self.request("price_range_breakout"))
        missing["dataset_id"] = "f" * 64
        response, code = execute(json.dumps(missing).encode(), self.data, self.reports, Path.cwd())
        self.assertEqual(code, 2)
        self.assertEqual(response["error"]["code"], "DATASET_NOT_FOUND")
        parquet = next(self.data.glob(f"*/EURUSD/H1/snapshots/{self.dataset_id}/candles.parquet"))
        payload = bytearray(parquet.read_bytes())
        payload[len(payload) // 2] ^= 0xFF
        parquet.write_bytes(payload)
        corrupted, code = execute(
            self.request("price_range_breakout"), self.data, self.reports, Path.cwd(),
        )
        self.assertEqual(code, 2)
        self.assertEqual(corrupted["error"]["code"], "DATASET_VERIFICATION_FAILED")

    def test_invalid_revision_fails_closed(self) -> None:
        request = json.loads(self.request("price_range_breakout"))
        request["implementation_revision"] = "not-a-revision"
        response, code = execute(json.dumps(request).encode(), self.data, self.reports, Path.cwd())
        self.assertEqual(code, 2)
        self.assertEqual(response["error"]["code"], "INVALID_REQUEST")


if __name__ == "__main__":
    unittest.main()
