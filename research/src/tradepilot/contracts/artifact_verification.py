"""Strict JSON contract for verifying existing immutable artifacts."""

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tradepilot.core.canonical import canonical_value
from tradepilot.data.integrity import IntegrityReport, verify_dataset
from tradepilot.reporting.storage import ReportVerification, verify_report


CONTRACT_VERSION = "tradepilot-artifact-verification/v1"
MAX_REQUEST_BYTES = 65_536
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
PROVIDER_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
INSTRUMENT_PATTERN = re.compile(r"^[A-Z]{6,12}$")
TIMEFRAME_PATTERN = re.compile(r"^[A-Z][A-Z0-9]{0,15}$")


class ContractRequestError(ValueError):
    def __init__(self, code: str, message: str, request_id: str = "unknown") -> None:
        super().__init__(message)
        self.code = code
        self.request_id = request_id


@dataclass(frozen=True, slots=True)
class ArtifactRoots:
    dataset_root: Path
    report_root: Path

    @classmethod
    def approved(cls, dataset_root: str | Path, report_root: str | Path) -> "ArtifactRoots":
        return cls(_approved_root(dataset_root, "dataset"), _approved_root(report_root, "report"))


def _approved_root(value: str | Path, label: str) -> Path:
    root = Path(value)
    try:
        resolved = root.resolve(strict=True)
    except OSError as exc:
        raise ValueError(f"approved {label} root is unavailable") from exc
    if not resolved.is_dir():
        raise ValueError(f"approved {label} root is not a directory")
    return resolved


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ContractRequestError("INVALID_REQUEST", f"duplicate field: {key}")
        value[key] = item
    return value


def decode_request(payload: bytes) -> dict[str, Any]:
    if len(payload) > MAX_REQUEST_BYTES:
        raise ContractRequestError("REQUEST_TOO_LARGE", "request exceeds 65536 bytes")
    try:
        value = json.loads(payload.decode("utf-8"), object_pairs_hook=_strict_object)
    except ContractRequestError:
        raise
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ContractRequestError("INVALID_JSON", "request must be valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise ContractRequestError("INVALID_REQUEST", "request root must be an object")
    return value


def _exact_fields(value: dict[str, Any], expected: set[str], label: str, request_id: str) -> None:
    unknown = sorted(set(value) - expected)
    missing = sorted(expected - set(value))
    if unknown:
        raise ContractRequestError("INVALID_REQUEST", f"unknown {label} fields: {', '.join(unknown)}", request_id)
    if missing:
        raise ContractRequestError("INVALID_REQUEST", f"missing {label} fields: {', '.join(missing)}", request_id)


def _string_field(
    value: dict[str, Any], name: str, pattern: re.Pattern[str], request_id: str,
) -> str:
    item = value.get(name)
    if not isinstance(item, str) or pattern.fullmatch(item) is None:
        raise ContractRequestError("INVALID_REQUEST", f"invalid {name}", request_id)
    return item


def _safe_child(root: Path, *parts: str) -> Path:
    candidate = root.joinpath(*parts).resolve(strict=False)
    if not candidate.is_relative_to(root):
        raise ContractRequestError("ARTIFACT_PATH_UNSAFE", "artifact location escapes approved root")
    return candidate


def _issue_values(issues: tuple[Any, ...]) -> list[dict[str, str]]:
    return [
        {"severity": str(issue.severity), "code": str(issue.code)}
        for issue in issues
    ]


def _error(request_id: str, code: str, message: str, *, details: object | None = None) -> dict[str, Any]:
    error: dict[str, Any] = {"code": code, "message": message, "retryable": False}
    if details is not None:
        error["details"] = canonical_value(details)
    return {
        "contract_version": CONTRACT_VERSION,
        "request_id": request_id,
        "status": "ERROR",
        "error": error,
    }


def request_error_response(error: ContractRequestError) -> dict[str, Any]:
    return _error(error.request_id, error.code, str(error))


def _success(request_id: str, kind: str, artifact_id: str, verification: dict[str, Any]) -> dict[str, Any]:
    return {
        "contract_version": CONTRACT_VERSION,
        "request_id": request_id,
        "status": "VERIFIED",
        "artifact": {"kind": kind, "artifact_id": artifact_id},
        "verification": canonical_value(verification),
    }


def _dataset_verification(
    request_id: str, artifact_id: str, path: Path,
) -> tuple[dict[str, Any], int]:
    if not path.exists():
        return _error(request_id, "ARTIFACT_NOT_FOUND", "dataset artifact does not exist"), 3
    report: IntegrityReport = verify_dataset(path)
    if report.dataset_id is not None and report.dataset_id != artifact_id:
        return _error(request_id, "ARTIFACT_ID_MISMATCH", "dataset content identity differs from request"), 3
    if not report.valid:
        return _error(
            request_id, "ARTIFACT_VERIFICATION_FAILED", "dataset integrity verification failed",
            details={"issues": _issue_values(report.issues)},
        ), 3
    manifest = json.loads((report.snapshot_path / "manifest.json").read_text(encoding="utf-8"))
    verification = {
        "dataset_id": report.dataset_id,
        "dataset_checksum": report.dataset_checksum,
        "parquet_checksum": report.parquet_checksum,
        "provider": report.provider,
        "instrument": report.instrument,
        "timeframe": report.timeframe,
        "row_count": report.row_count,
        "first_timestamp": report.first_timestamp,
        "last_timestamp": report.last_timestamp,
        "retrieval_count": report.retrieval_count,
        "schema_version": manifest.get("schema_version"),
        "timestamp_convention": manifest.get("timestamp_convention"),
        "price_basis": manifest.get("price_basis"),
        "base_currency": manifest.get("base_currency"),
        "quote_currency": manifest.get("quote_currency"),
        "pip_size": manifest.get("pip_size"),
        "price_precision": manifest.get("price_precision"),
        "source_artifacts_checksum": manifest.get("source_artifacts_sha256"),
        "quality": report.quality_report.to_dict() if report.quality_report else None,
    }
    return _success(request_id, "dataset", artifact_id, verification), 0


def _report_verification(
    request_id: str, artifact_id: str, path: Path,
) -> tuple[dict[str, Any], int]:
    if not path.exists():
        return _error(request_id, "ARTIFACT_NOT_FOUND", "candidate report artifact does not exist"), 3
    report: ReportVerification = verify_report(path)
    if report.report_id is not None and report.report_id != artifact_id:
        return _error(request_id, "ARTIFACT_ID_MISMATCH", "report content identity differs from request"), 3
    if not report.valid:
        return _error(
            request_id, "ARTIFACT_VERIFICATION_FAILED", "candidate report verification failed",
            details={"issues": _issue_values(report.issues)},
        ), 3
    envelope = json.loads((path / "report.json").read_text(encoding="utf-8"))
    content = envelope["content"]
    verification = {
        "report_id": report.report_id,
        "schema_version": content.get("schema_version"),
        "dataset_id": content.get("dataset_id"),
        "dataset_checksum": content.get("dataset_checksum"),
        "instrument": content.get("instrument"),
        "timeframe": content.get("timeframe"),
        "dataset_first_timestamp": content.get("dataset_first_timestamp"),
        "dataset_last_timestamp": content.get("dataset_last_timestamp"),
        "strategy_name": content.get("strategy_name"),
        "strategy_version": content.get("strategy_version"),
        "configuration_fingerprint": content.get("configuration_fingerprint"),
        "strategy_configuration": content.get("strategy_configuration"),
        "indicator_parameters": content.get("indicator_parameters"),
        "session_calendar_id": content.get("session_calendar_id"),
        "research_engine_version": content.get("research_engine_version"),
        "implementation_revision": content.get("implementation_revision"),
        "signal_count": report.signal_count,
    }
    return _success(request_id, "candidate_report", artifact_id, verification), 0


def process_request(payload: bytes, roots: ArtifactRoots) -> tuple[dict[str, Any], int]:
    try:
        request = decode_request(payload)
        preliminary_id = request.get("request_id")
        request_id = (
            preliminary_id
            if isinstance(preliminary_id, str) and REQUEST_ID_PATTERN.fullmatch(preliminary_id)
            else "unknown"
        )
        _exact_fields(
            request, {"contract_version", "request_id", "operation", "artifact"},
            "request", request_id,
        )
        request_id = _string_field(request, "request_id", REQUEST_ID_PATTERN, "unknown")
        if request["contract_version"] != CONTRACT_VERSION:
            raise ContractRequestError("UNSUPPORTED_CONTRACT", "unsupported contract version", request_id)
        if request["operation"] != "verify_artifact":
            raise ContractRequestError("UNSUPPORTED_OPERATION", "unsupported operation", request_id)
        artifact = request["artifact"]
        if not isinstance(artifact, dict):
            raise ContractRequestError("INVALID_REQUEST", "artifact must be an object", request_id)
        kind = artifact.get("kind")
        if kind == "dataset":
            _exact_fields(
                artifact, {"kind", "artifact_id", "provider", "instrument", "timeframe"},
                "artifact", request_id,
            )
            artifact_id = _string_field(artifact, "artifact_id", SHA256_PATTERN, request_id)
            provider = _string_field(artifact, "provider", PROVIDER_PATTERN, request_id)
            instrument = _string_field(artifact, "instrument", INSTRUMENT_PATTERN, request_id)
            timeframe = _string_field(artifact, "timeframe", TIMEFRAME_PATTERN, request_id)
            path = _safe_child(roots.dataset_root, provider, instrument, timeframe, "snapshots", artifact_id)
            return _dataset_verification(request_id, artifact_id, path)
        if kind == "candidate_report":
            _exact_fields(artifact, {"kind", "artifact_id"}, "artifact", request_id)
            artifact_id = _string_field(artifact, "artifact_id", SHA256_PATTERN, request_id)
            path = _safe_child(roots.report_root, artifact_id)
            return _report_verification(request_id, artifact_id, path)
        raise ContractRequestError("UNSUPPORTED_ARTIFACT_KIND", "unsupported artifact kind", request_id)
    except ContractRequestError as exc:
        return request_error_response(exc), 2


__all__ = [
    "ArtifactRoots", "CONTRACT_VERSION", "ContractRequestError",
    "MAX_REQUEST_BYTES", "decode_request", "process_request", "request_error_response",
]
