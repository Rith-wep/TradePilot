import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ingestion_helpers import EURUSD, START, raw_candle
from reporting_helpers import build_run, create_context
from tradepilot.contracts.artifact_verification import (
    CONTRACT_VERSION,
    MAX_REQUEST_BYTES,
    ArtifactRoots,
    process_request,
)
from tradepilot.data.normalization import normalize_provider_candle
from tradepilot.data.storage import ParquetDatasetStore
from tradepilot.reporting.storage import ReportStorage


FIXTURES = Path(__file__).parents[1] / "fixtures" / "contracts"
NOW = datetime(2025, 1, 2, tzinfo=timezone.utc)


def fixture(name: str) -> dict[str, object]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def encoded(value: dict[str, object]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


class ArtifactVerificationContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.datasets = tempfile.TemporaryDirectory()
        self.reports = tempfile.TemporaryDirectory()
        self.addCleanup(self.datasets.cleanup)
        self.addCleanup(self.reports.cleanup)
        self.roots = ArtifactRoots.approved(self.datasets.name, self.reports.name)

    def _stored_dataset(self):
        candle = normalize_provider_candle(
            raw_candle(0), instrument=EURUSD, provider="mock",
            dataset_version="contract-v1", is_synthetic=True,
        )
        return ParquetDatasetStore(self.datasets.name).save(
            "mock", EURUSD, "H1", [candle],
            retrieved_at=NOW, request_start=START,
            request_end=START + timedelta(hours=1),
        )

    def _stored_report(self):
        _, integrity, calendar, config, strategy, fingerprint, setups = create_context(self.datasets.name)
        run = build_run(integrity, calendar, config, strategy, fingerprint, setups)
        return ReportStorage(self.reports.name).save(run)

    def test_committed_contract_schemas_are_valid_json_and_versioned(self) -> None:
        schema_root = Path(__file__).parents[1] / "contracts"
        for name in (
            "artifact-verification-v1.request.schema.json",
            "artifact-verification-v1.response.schema.json",
        ):
            schema = json.loads((schema_root / name).read_text(encoding="utf-8"))
            self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
            self.assertIn("artifact-verification-v1", schema["$id"])

    def test_valid_dataset_contract_is_deterministic_and_lossless(self) -> None:
        stored = self._stored_dataset()
        request = fixture("verify-dataset-request.json")
        request["artifact"]["artifact_id"] = stored.dataset_id
        first, first_code = process_request(encoded(request), self.roots)
        second, second_code = process_request(encoded(request), self.roots)
        self.assertEqual((first_code, second_code), (0, 0))
        self.assertEqual(first, second)
        self.assertEqual(first["status"], "VERIFIED")
        verification = first["verification"]
        self.assertEqual(verification["dataset_id"], stored.dataset_id)
        self.assertEqual(verification["dataset_checksum"], stored.dataset_checksum)
        self.assertEqual(verification["parquet_checksum"], stored.file_checksum)
        self.assertEqual(verification["pip_size"], "0.0001")
        self.assertEqual(verification["first_timestamp"], "2024-01-02T00:00:00Z")

    def test_valid_report_preserves_provenance_and_decimal_strings(self) -> None:
        stored = self._stored_report()
        request = fixture("verify-report-request.json")
        request["artifact"]["artifact_id"] = stored.report_id
        response, code = process_request(encoded(request), self.roots)
        self.assertEqual(code, 0)
        verification = response["verification"]
        self.assertEqual(verification["report_id"], stored.report_id)
        self.assertRegex(verification["dataset_id"], r"^[0-9a-f]{64}$")
        self.assertRegex(verification["dataset_checksum"], r"^[0-9a-f]{64}$")
        self.assertEqual(verification["dataset_first_timestamp"], "2024-01-01T00:00:00Z")
        self.assertIsInstance(verification["strategy_configuration"], list)
        self.assertNotIn("report_path", verification)
        self.assertNotIn("snapshot_path", verification)

    def test_missing_corrupt_and_mismatched_artifacts_fail_closed(self) -> None:
        missing = fixture("verify-dataset-request.json")
        response, code = process_request(encoded(missing), self.roots)
        self.assertEqual((code, response["error"]["code"]), (3, "ARTIFACT_NOT_FOUND"))

        stored = self._stored_dataset()
        payload = bytearray(stored.parquet_path.read_bytes())
        payload[len(payload) // 2] ^= 0xFF
        stored.parquet_path.write_bytes(payload)
        corrupt = fixture("verify-dataset-request.json")
        corrupt["artifact"]["artifact_id"] = stored.dataset_id
        response, code = process_request(encoded(corrupt), self.roots)
        self.assertEqual((code, response["error"]["code"]), (3, "ARTIFACT_VERIFICATION_FAILED"))
        self.assertNotIn(self.datasets.name, json.dumps(response))

        separate = tempfile.TemporaryDirectory()
        self.addCleanup(separate.cleanup)
        self.datasets.cleanup()
        self.datasets = separate
        self.roots = ArtifactRoots.approved(self.datasets.name, self.reports.name)
        stored = self._stored_dataset()
        requested_id = "f" * 64
        wrong_directory = stored.snapshot_path.parent / requested_id
        shutil.copytree(stored.snapshot_path, wrong_directory)
        mismatch = fixture("verify-dataset-request.json")
        mismatch["artifact"]["artifact_id"] = requested_id
        response, code = process_request(encoded(mismatch), self.roots)
        self.assertEqual((code, response["error"]["code"]), (3, "ARTIFACT_ID_MISMATCH"))

    def test_corrupted_and_mismatched_reports_fail_closed(self) -> None:
        stored = self._stored_report()
        requested_id = "e" * 64
        copied = Path(self.reports.name) / requested_id
        shutil.copytree(stored.report_path.parent, copied)
        mismatch = fixture("verify-report-request.json")
        mismatch["artifact"]["artifact_id"] = requested_id
        response, code = process_request(encoded(mismatch), self.roots)
        self.assertEqual((code, response["error"]["code"]), (3, "ARTIFACT_ID_MISMATCH"))

        stored.report_path.write_text("{}", encoding="utf-8")
        corrupt = fixture("verify-report-request.json")
        corrupt["artifact"]["artifact_id"] = stored.report_id
        response, code = process_request(encoded(corrupt), self.roots)
        self.assertEqual((code, response["error"]["code"]), (3, "ARTIFACT_VERIFICATION_FAILED"))
        self.assertNotIn(self.reports.name, json.dumps(response))

    def test_unsupported_unknown_invalid_and_oversized_requests_are_rejected(self) -> None:
        unsupported = fixture("unsupported-contract-request.json")
        response, code = process_request(encoded(unsupported), self.roots)
        self.assertEqual((code, response["error"]["code"]), (2, "UNSUPPORTED_CONTRACT"))

        unknown = fixture("verify-report-request.json")
        unknown["unexpected"] = True
        response, code = process_request(encoded(unknown), self.roots)
        self.assertEqual((code, response["error"]["code"]), (2, "INVALID_REQUEST"))

        duplicate = (
            b'{"contract_version":"tradepilot-artifact-verification/v1",'
            b'"request_id":"duplicate-1","request_id":"duplicate-2",'
            b'"operation":"verify_artifact","artifact":{}}'
        )
        response, code = process_request(duplicate, self.roots)
        self.assertEqual((code, response["error"]["code"]), (2, "INVALID_REQUEST"))

        unsupported_kind = fixture("verify-report-request.json")
        unsupported_kind["artifact"]["kind"] = "simulation"
        response, code = process_request(encoded(unsupported_kind), self.roots)
        self.assertEqual(
            (code, response["error"]["code"]), (2, "UNSUPPORTED_ARTIFACT_KIND"),
        )

        invalid = fixture("verify-dataset-request.json")
        invalid["artifact"]["provider"] = "../../escape"
        response, code = process_request(encoded(invalid), self.roots)
        self.assertEqual((code, response["error"]["code"]), (2, "INVALID_REQUEST"))

        response, code = process_request(b"{" + b" " * MAX_REQUEST_BYTES, self.roots)
        self.assertEqual((code, response["error"]["code"]), (2, "REQUEST_TOO_LARGE"))

    def test_cli_stdout_is_one_machine_readable_error_and_stderr_is_empty(self) -> None:
        request = (FIXTURES / "verify-report-request.json").read_bytes()
        completed = subprocess.run(
            [
                sys.executable, "-m", "tradepilot.contracts",
                "--dataset-root", self.datasets.name,
                "--report-root", self.reports.name,
            ],
            input=request, capture_output=True, check=False,
        )
        self.assertEqual(completed.returncode, 3)
        self.assertEqual(completed.stderr, b"")
        lines = completed.stdout.splitlines()
        self.assertEqual(len(lines), 1)
        response = json.loads(lines[0])
        self.assertEqual(response, fixture("missing-report-response.json"))
        self.assertEqual(response["contract_version"], CONTRACT_VERSION)


if __name__ == "__main__":
    unittest.main()
