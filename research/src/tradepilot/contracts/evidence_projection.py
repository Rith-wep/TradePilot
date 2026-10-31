"""Bounded projection of verified immutable candidate-report evidence."""

import json
import re
from pathlib import Path
from typing import Any

from tradepilot.core.canonical import canonical_json_bytes, canonical_value, sha256_hex
from tradepilot.reporting.storage import verify_report


CONTRACT_VERSION = "tradepilot-candidate-evidence/v1"
MAX_REQUEST_BYTES = 65_536
MAX_CANDIDATES = 100
SHA256 = re.compile(r"^[0-9a-f]{64}$")
REQUEST_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
EVIDENCE_ID = re.compile(r"^([0-9a-f]{64})\.([0-9]{8})\.([0-9a-f]{64})$")


class EvidenceRequestError(ValueError):
    def __init__(self, code: str, message: str, request_id: str = "unknown") -> None:
        super().__init__(message)
        self.code = code
        self.request_id = request_id


def approved_report_root(value: str | Path) -> Path:
    try:
        root = Path(value).resolve(strict=True)
    except OSError as exc:
        raise ValueError("approved report root is unavailable") from exc
    if not root.is_dir():
        raise ValueError("approved report root is not a directory")
    return root


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise EvidenceRequestError("INVALID_REQUEST", f"duplicate field: {key}")
        result[key] = value
    return result


def _decode(payload: bytes) -> dict[str, Any]:
    if len(payload) > MAX_REQUEST_BYTES:
        raise EvidenceRequestError("REQUEST_TOO_LARGE", "request exceeds 65536 bytes")
    try:
        value = json.loads(payload.decode("utf-8"), object_pairs_hook=_strict_object)
    except EvidenceRequestError:
        raise
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise EvidenceRequestError("INVALID_JSON", "request must be valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise EvidenceRequestError("INVALID_REQUEST", "request root must be an object")
    return value


def _exact(value: dict[str, Any], fields: set[str], request_id: str) -> None:
    if set(value) != fields:
        raise EvidenceRequestError("INVALID_REQUEST", "request fields do not match operation", request_id)


def _error(request_id: str, code: str, message: str) -> dict[str, Any]:
    return {
        "contract_version": CONTRACT_VERSION,
        "request_id": request_id,
        "status": "ERROR",
        "error": {"code": code, "message": message, "retryable": False},
    }


def _report_content(root: Path, report_id: str, request_id: str) -> dict[str, Any]:
    path = root.joinpath(report_id).resolve(strict=False)
    if not path.is_relative_to(root):
        raise EvidenceRequestError("ARTIFACT_PATH_UNSAFE", "report path is unsafe", request_id)
    if not path.exists():
        raise EvidenceRequestError("ARTIFACT_NOT_FOUND", "candidate report does not exist", request_id)
    verification = verify_report(path)
    if verification.report_id is not None and verification.report_id != report_id:
        raise EvidenceRequestError("ARTIFACT_ID_MISMATCH", "candidate report identity mismatch", request_id)
    if not verification.valid:
        raise EvidenceRequestError(
            "ARTIFACT_VERIFICATION_FAILED", "candidate report integrity verification failed", request_id,
        )
    try:
        envelope = json.loads((path / "report.json").read_text(encoding="utf-8"))
        content = envelope["content"]
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise EvidenceRequestError(
            "ARTIFACT_VERIFICATION_FAILED", "candidate report cannot be projected", request_id,
        ) from exc
    if not isinstance(content, dict):
        raise EvidenceRequestError("ARTIFACT_VERIFICATION_FAILED", "report content is invalid", request_id)
    return content


def _candidate_id(report_id: str, ordinal: int, signal: dict[str, Any]) -> str:
    return f"{report_id}.{ordinal:08d}.{sha256_hex(canonical_json_bytes(signal))}"


def _project(report_id: str, ordinal: int, content: dict[str, Any]) -> dict[str, Any]:
    signals = content["signals"]
    signal = signals[ordinal]
    setup = signal["setup"]
    evidence_id = _candidate_id(report_id, ordinal, signal)
    limitations = [
        "HISTORICAL_RESEARCH_ONLY",
        "NOT_LIVE_SIGNAL",
        "NOT_TRADING_RECOMMENDATION",
        "NO_PROFITABILITY_CLAIM",
    ]
    if setup.get("structural_invalidation_reference") is not None:
        limitations.append("STRUCTURAL_INVALIDATION_REFERENCE_IS_NOT_AN_EXECUTABLE_STOP")
    return canonical_value({
        "candidateEvidenceId": evidence_id,
        "reportId": report_id,
        "datasetId": signal.get("dataset_id"),
        "datasetChecksum": signal.get("dataset_checksum"),
        "instrument": setup.get("instrument"),
        "timeframe": setup.get("timeframe"),
        "detectionCandleOpenTime": setup.get("detection_candle_open_time"),
        "observableAt": setup.get("observable_at"),
        "direction": setup.get("direction"),
        "setupType": setup.get("setup_type"),
        "strategy": {
            "name": setup.get("strategy_name"),
            "version": setup.get("strategy_version"),
            "configurationFingerprint": setup.get("configuration_fingerprint"),
        },
        "indicatorContext": {
            "values": setup.get("indicator_values", []),
            "parameters": content.get("indicator_parameters", []),
        },
        "ruleEvidence": setup.get("rule_evidence", []),
        "structuralInvalidationReference": setup.get("structural_invalidation_reference"),
        "provenance": {
            "reportSchemaVersion": content.get("schema_version"),
            "researchEngineVersion": content.get("research_engine_version"),
            "implementationRevision": content.get("implementation_revision"),
            "sessionCalendarId": content.get("session_calendar_id"),
        },
        "classification": "HISTORICAL_RESEARCH",
        "liveSignal": False,
        "limitations": limitations,
    })


def process_request(payload: bytes, report_root: Path) -> tuple[dict[str, Any], int]:
    request_id = "unknown"
    try:
        request = _decode(payload)
        candidate_id = request.get("request_id")
        if isinstance(candidate_id, str) and REQUEST_ID.fullmatch(candidate_id):
            request_id = candidate_id
        else:
            raise EvidenceRequestError("INVALID_REQUEST", "invalid request_id")
        version = request.get("contract_version")
        if version != CONTRACT_VERSION:
            raise EvidenceRequestError("UNSUPPORTED_CONTRACT", "unsupported contract version", request_id)
        operation = request.get("operation")
        if operation == "list_candidates":
            _exact(request, {"contract_version", "request_id", "operation", "report_id", "offset", "limit"}, request_id)
            report_id = request.get("report_id")
            offset = request.get("offset")
            limit = request.get("limit")
            if not isinstance(report_id, str) or SHA256.fullmatch(report_id) is None:
                raise EvidenceRequestError("INVALID_REQUEST", "invalid report_id", request_id)
            if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
                raise EvidenceRequestError("INVALID_REQUEST", "invalid offset", request_id)
            if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= MAX_CANDIDATES:
                raise EvidenceRequestError("INVALID_REQUEST", "invalid limit", request_id)
            content = _report_content(report_root, report_id, request_id)
            signals = content.get("signals")
            if not isinstance(signals, list):
                raise EvidenceRequestError("ARTIFACT_VERIFICATION_FAILED", "report signals are invalid", request_id)
            end = min(offset + limit, len(signals))
            candidates = [_project(report_id, ordinal, content) for ordinal in range(offset, end)]
            response = {
                "contract_version": CONTRACT_VERSION,
                "request_id": request_id,
                "status": "OK",
                "operation": operation,
                "report_id": report_id,
                "candidates": candidates,
                "next_offset": end if end < len(signals) else None,
                "total_count": len(signals),
            }
            return response, 0
        if operation == "get_evidence":
            _exact(request, {"contract_version", "request_id", "operation", "evidence_id"}, request_id)
            evidence_id = request.get("evidence_id")
            match = EVIDENCE_ID.fullmatch(evidence_id) if isinstance(evidence_id, str) else None
            if match is None:
                raise EvidenceRequestError("INVALID_REQUEST", "invalid evidence_id", request_id)
            report_id, ordinal_text, digest = match.groups()
            content = _report_content(report_root, report_id, request_id)
            signals = content.get("signals")
            ordinal = int(ordinal_text)
            if not isinstance(signals, list) or ordinal >= len(signals):
                raise EvidenceRequestError("EVIDENCE_NOT_FOUND", "candidate evidence does not exist", request_id)
            projected = _project(report_id, ordinal, content)
            if not projected["candidateEvidenceId"].endswith(f".{digest}"):
                raise EvidenceRequestError("EVIDENCE_ID_MISMATCH", "candidate evidence identity mismatch", request_id)
            return {
                "contract_version": CONTRACT_VERSION,
                "request_id": request_id,
                "status": "OK",
                "operation": operation,
                "evidence": projected,
            }, 0
        raise EvidenceRequestError("UNSUPPORTED_OPERATION", "unsupported operation", request_id)
    except EvidenceRequestError as exc:
        request_codes = {"INVALID_JSON", "INVALID_REQUEST", "REQUEST_TOO_LARGE", "UNSUPPORTED_CONTRACT", "UNSUPPORTED_OPERATION"}
        return _error(exc.request_id, exc.code, str(exc)), 2 if exc.code in request_codes else 3
