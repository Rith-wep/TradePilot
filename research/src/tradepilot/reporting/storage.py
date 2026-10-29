"""Concurrency-safe immutable storage and verification for research reports."""

import json
import os
import shutil
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal

from tradepilot.core.canonical import canonical_json_bytes, sha256_hex
from tradepilot.reporting.models import REPORT_SCHEMA_VERSION, ResearchRun, StoredReport


class ReportStorageError(RuntimeError):
    """Raised when immutable report publication or reuse is unsafe."""


@dataclass(frozen=True, slots=True)
class ReportVerificationIssue:
    severity: Literal["error", "warning"]
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class ReportVerification:
    valid: bool
    report_id: str | None
    report_path: Path
    signal_count: int | None
    issues: tuple[ReportVerificationIssue, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "valid": self.valid,
            "report_id": self.report_id,
            "report_path": str(self.report_path),
            "signal_count": self.signal_count,
            "issues": [asdict(issue) for issue in self.issues],
        }


def report_identifier(content: object) -> str:
    return sha256_hex(canonical_json_bytes(content))


def _parse_utc(value: object) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("timestamp must be a UTC string ending in Z")
    timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if timestamp.utcoffset() != timedelta(0):
        raise ValueError("timestamp must use UTC")
    return timestamp


def verify_report(path: str | Path) -> ReportVerification:
    directory = Path(path)
    report_path = directory / "report.json" if directory.is_dir() else directory
    directory = report_path.parent
    issues: list[ReportVerificationIssue] = []
    if not report_path.exists():
        issues.append(ReportVerificationIssue("error", "missing_report", f"report file is missing: {report_path}"))
        return ReportVerification(False, None, report_path, None, tuple(issues))
    try:
        raw = report_path.read_bytes()
        envelope = json.loads(raw.decode("utf-8"))
        if not isinstance(envelope, dict) or not isinstance(envelope.get("content"), dict):
            raise ValueError("report root and content must be objects")
        canonical_envelope = canonical_json_bytes(envelope)
        if raw != canonical_envelope:
            issues.append(ReportVerificationIssue("error", "noncanonical_report", "report bytes are not canonical JSON"))
        embedded_id = envelope.get("report_id")
        calculated_id = report_identifier(envelope["content"])
        if embedded_id != calculated_id:
            issues.append(ReportVerificationIssue("error", "report_id_mismatch", "report ID does not match canonical content"))
        if directory.name != embedded_id:
            issues.append(ReportVerificationIssue("error", "report_directory_mismatch", "directory name does not match report ID"))
        content = envelope["content"]
        if content.get("schema_version") != REPORT_SCHEMA_VERSION:
            issues.append(ReportVerificationIssue("error", "schema_version_mismatch", "unsupported report schema"))
        signals = content.get("signals")
        if not isinstance(signals, list):
            raise ValueError("signals must be an array")
        timeframe = content.get("timeframe")
        duration = timedelta(hours=1) if timeframe == "H1" else None
        if duration is None:
            issues.append(ReportVerificationIssue("error", "unsupported_timeframe", "report timeframe duration is unsupported"))
        seen: set[tuple[object, ...]] = set()
        previous_detection: datetime | None = None
        for signal in signals:
            if not isinstance(signal, dict) or not isinstance(signal.get("setup"), dict):
                raise ValueError("each signal and setup must be objects")
            setup = signal["setup"]
            detection = _parse_utc(setup.get("detection_candle_open_time"))
            observable = _parse_utc(setup.get("observable_at"))
            if duration is not None and observable != detection + duration:
                issues.append(ReportVerificationIssue("error", "invalid_observable_time", "observable time is not candle open plus duration"))
            if previous_detection is not None and detection < previous_detection:
                issues.append(ReportVerificationIssue("error", "signals_out_of_order", "signals are not chronological"))
            previous_detection = detection
            key = (
                setup.get("strategy_name"), setup.get("strategy_version"),
                setup.get("instrument"), setup.get("timeframe"),
                setup.get("direction"), setup.get("detection_candle_open_time"),
            )
            if key in seen:
                issues.append(ReportVerificationIssue("error", "duplicate_signal", "duplicate signal identity"))
            seen.add(key)
            if signal.get("dataset_id") != content.get("dataset_id") or signal.get("dataset_checksum") != content.get("dataset_checksum"):
                issues.append(ReportVerificationIssue("error", "signal_dataset_mismatch", "signal dataset provenance differs from report"))
            if (
                setup.get("strategy_name") != content.get("strategy_name")
                or setup.get("strategy_version") != content.get("strategy_version")
                or setup.get("configuration_fingerprint") != content.get("configuration_fingerprint")
                or setup.get("instrument") != content.get("instrument")
                or setup.get("timeframe") != content.get("timeframe")
            ):
                issues.append(ReportVerificationIssue("error", "signal_provenance_mismatch", "signal provenance differs from report"))
        valid = not any(issue.severity == "error" for issue in issues)
        return ReportVerification(valid, str(embedded_id) if isinstance(embedded_id, str) else None, report_path, len(signals), tuple(issues))
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        issues.append(ReportVerificationIssue("error", "invalid_report", str(exc)))
        return ReportVerification(False, None, report_path, None, tuple(issues))


def _write_synced(path: Path, payload: bytes) -> None:
    with path.open("xb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


class ReportStorage:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def _publish_run_metadata(self, directory: Path, report_id: str, created_at: datetime) -> Path:
        metadata = {"report_id": report_id, "created_at": created_at}
        payload = canonical_json_bytes(metadata)
        event_id = sha256_hex(payload)
        runs = directory / "runs"
        runs.mkdir(exist_ok=True)
        target = runs / f"{event_id}.json"
        if target.exists():
            if target.read_bytes() != payload:
                raise ReportStorageError(f"conflicting run metadata exists: {target}")
            return target
        temporary = runs / f".metadata-{uuid.uuid4().hex}.tmp"
        _write_synced(temporary, payload)
        try:
            try:
                os.link(temporary, target)
            except FileExistsError:
                if target.read_bytes() != payload:
                    raise ReportStorageError(f"conflicting run metadata exists: {target}")
        finally:
            temporary.unlink(missing_ok=True)
        return target

    def save(self, run: ResearchRun) -> StoredReport:
        report_id = report_identifier(run.content)
        final = self.root / report_id
        report_payload = canonical_json_bytes({"report_id": report_id, "content": run.content})
        self.root.mkdir(parents=True, exist_ok=True)
        if final.exists():
            verification = verify_report(final)
            if not verification.valid or verification.report_id != report_id:
                raise ReportStorageError(f"existing report is corrupt or conflicting: {final}")
            metadata_path = self._publish_run_metadata(final, report_id, run.created_at)
            return StoredReport(report_id, final / "report.json", metadata_path, True)

        staged = self.root / f".staging-{uuid.uuid4().hex}"
        staged.mkdir()
        try:
            _write_synced(staged / "report.json", report_payload)
            runs = staged / "runs"
            runs.mkdir()
            metadata = {"report_id": report_id, "created_at": run.created_at}
            metadata_payload = canonical_json_bytes(metadata)
            metadata_name = f"{sha256_hex(metadata_payload)}.json"
            _write_synced(runs / metadata_name, metadata_payload)
            try:
                os.rename(staged, final)
            except OSError:
                if not final.exists():
                    raise
                verification = verify_report(final)
                if not verification.valid or verification.report_id != report_id:
                    raise ReportStorageError(f"concurrently published report is invalid: {final}")
                shutil.rmtree(staged)
                metadata_path = self._publish_run_metadata(final, report_id, run.created_at)
                return StoredReport(report_id, final / "report.json", metadata_path, True)
            return StoredReport(report_id, final / "report.json", final / "runs" / metadata_name, False)
        except Exception:
            if staged.exists():
                shutil.rmtree(staged)
            raise
