import json
import shutil
import tempfile
import unittest
from pathlib import Path

from reporting_helpers import build_run, create_context
from tradepilot.contracts.evidence_projection import (
    CONTRACT_VERSION,
    MAX_REQUEST_BYTES,
    approved_report_root,
    process_request,
)
from tradepilot.reporting.storage import ReportStorage


def encoded(value: dict[str, object]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


class EvidenceProjectionContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.datasets = tempfile.TemporaryDirectory()
        self.reports = tempfile.TemporaryDirectory()
        self.addCleanup(self.datasets.cleanup)
        self.addCleanup(self.reports.cleanup)
        self.root = approved_report_root(self.reports.name)

    def _report(self, *, empty: bool = False):
        _, integrity, calendar, config, strategy, fingerprint, setups = create_context(self.datasets.name)
        run = build_run(
            integrity, calendar, config, strategy, fingerprint,
            () if empty else setups,
        )
        return ReportStorage(self.reports.name).save(run)

    def _list_request(self, report_id: str, **updates: object) -> dict[str, object]:
        request: dict[str, object] = {
            "contract_version": CONTRACT_VERSION,
            "request_id": "evidence-list-1",
            "operation": "list_candidates",
            "report_id": report_id,
            "offset": 0,
            "limit": 25,
        }
        request.update(updates)
        return request

    def test_valid_list_and_detail_are_deterministic_and_historical(self) -> None:
        stored = self._report()
        first, first_code = process_request(encoded(self._list_request(stored.report_id)), self.root)
        second, second_code = process_request(encoded(self._list_request(stored.report_id)), self.root)
        self.assertEqual((first_code, second_code), (0, 0))
        self.assertEqual(first, second)
        candidate = first["candidates"][0]
        self.assertEqual(candidate["classification"], "HISTORICAL_RESEARCH")
        self.assertIs(candidate["liveSignal"], False)
        self.assertRegex(candidate["candidateEvidenceId"], rf"^{stored.report_id}\.00000000\.[0-9a-f]{{64}}$")
        self.assertIsInstance(candidate["structuralInvalidationReference"], str)
        detail_request = {
            "contract_version": CONTRACT_VERSION,
            "request_id": "evidence-detail-1",
            "operation": "get_evidence",
            "evidence_id": candidate["candidateEvidenceId"],
        }
        detail, code = process_request(encoded(detail_request), self.root)
        self.assertEqual(code, 0)
        self.assertEqual(detail["evidence"], candidate)

    def test_empty_missing_corrupt_mismatch_and_bounds_fail_closed(self) -> None:
        empty = self._report(empty=True)
        response, code = process_request(encoded(self._list_request(empty.report_id)), self.root)
        self.assertEqual(code, 0)
        self.assertEqual(response["candidates"], [])
        self.assertEqual(response["total_count"], 0)

        response, code = process_request(encoded(self._list_request("f" * 64)), self.root)
        self.assertEqual((code, response["error"]["code"]), (3, "ARTIFACT_NOT_FOUND"))

        stored = self._report()
        stored.report_path.write_text("{}", encoding="utf-8")
        response, code = process_request(encoded(self._list_request(stored.report_id)), self.root)
        self.assertEqual((code, response["error"]["code"]), (3, "ARTIFACT_VERIFICATION_FAILED"))

        separate = tempfile.TemporaryDirectory()
        self.addCleanup(separate.cleanup)
        self.reports.cleanup()
        self.reports = separate
        self.root = approved_report_root(self.reports.name)
        stored = self._report()
        wrong = "e" * 64
        shutil.copytree(stored.report_path.parent, Path(self.reports.name) / wrong)
        response, code = process_request(encoded(self._list_request(wrong)), self.root)
        self.assertEqual((code, response["error"]["code"]), (3, "ARTIFACT_ID_MISMATCH"))

        response, code = process_request(
            encoded(self._list_request(stored.report_id, limit=101)), self.root,
        )
        self.assertEqual((code, response["error"]["code"]), (2, "INVALID_REQUEST"))
        response, code = process_request(b"{" + b" " * MAX_REQUEST_BYTES, self.root)
        self.assertEqual((code, response["error"]["code"]), (2, "REQUEST_TOO_LARGE"))

    def test_schemas_are_committed_and_versioned(self) -> None:
        root = Path(__file__).parents[1] / "contracts"
        for name in (
            "candidate-evidence-v1.request.schema.json",
            "candidate-evidence-v1.response.schema.json",
        ):
            schema = json.loads((root / name).read_text(encoding="utf-8"))
            self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
            self.assertIn("candidate-evidence-v1", schema["$id"])


if __name__ == "__main__":
    unittest.main()
