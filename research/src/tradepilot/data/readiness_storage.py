"""Immutable content-addressed storage for real-data readiness evidence."""

import json
import os
from dataclasses import dataclass
from pathlib import Path

from tradepilot.data.readiness import ReadinessReport
from tradepilot.core.canonical import canonical_json_bytes, canonical_value, sha256_hex


class ReadinessStorageError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class StoredReadinessReport:
    report_id: str
    path: Path
    reused: bool


class ReadinessReportStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def save(self, report: ReadinessReport) -> StoredReadinessReport:
        expected = sha256_hex(canonical_json_bytes(report.content))
        if report.report_id != expected:
            raise ReadinessStorageError("readiness report identity does not match content")
        directory = self.root / report.report_id
        path = directory / "readiness.json"
        payload = {"report_id": report.report_id, "content": canonical_value(report.content)}
        encoded = json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
        if path.exists():
            try:
                existing = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise ReadinessStorageError("existing readiness report is corrupted") from exc
            if existing != payload:
                raise ReadinessStorageError("existing readiness report conflicts with immutable content")
            return StoredReadinessReport(report.report_id, path, True)
        if directory.exists():
            raise ReadinessStorageError("incomplete readiness report directory exists")
        staging = self.root / f".{report.report_id}.tmp"
        if staging.exists():
            raise ReadinessStorageError("readiness report staging path already exists")
        staging.mkdir(parents=True)
        temporary = staging / "readiness.json"
        temporary.write_text(encoded, encoding="utf-8")
        self.root.mkdir(parents=True, exist_ok=True)
        try:
            os.replace(staging, directory)
        except OSError as exc:
            if directory.exists() and path.exists():
                try:
                    existing = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError) as read_exc:
                    raise ReadinessStorageError("concurrent readiness report is corrupted") from read_exc
                if existing == payload:
                    return StoredReadinessReport(report.report_id, path, True)
            raise ReadinessStorageError("cannot atomically publish readiness report") from exc
        return StoredReadinessReport(report.report_id, path, False)


def verify_readiness_report(path: str | Path) -> bool:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        report_id = payload["report_id"]
        content = payload["content"]
        return isinstance(report_id, str) and sha256_hex(canonical_json_bytes(content)) == report_id
    except (OSError, KeyError, TypeError, json.JSONDecodeError, ValueError):
        return False
