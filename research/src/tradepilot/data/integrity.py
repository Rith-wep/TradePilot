"""Independent integrity verification for immutable dataset snapshots."""

import json
from dataclasses import asdict, dataclass
from datetime import timezone
from decimal import Decimal
from pathlib import Path
from typing import Literal

import pyarrow as pa
import pyarrow.parquet as pq

from tradepilot.data.models import Candle, Instrument
from tradepilot.data.storage import (
    PRICE_COLUMNS,
    SCHEMA_VERSION,
    canonical_dataset_checksum,
    checksum_bytes,
    dataset_identifier,
    parquet_schema,
)
from tradepilot.data.validation import QualityReport, validate_candles


@dataclass(frozen=True, slots=True)
class IntegrityIssue:
    severity: Literal["error", "warning"]
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class IntegrityReport:
    valid: bool
    snapshot_path: Path
    dataset_id: str | None
    provider: str | None
    instrument: str | None
    timeframe: str | None
    row_count: int | None
    first_timestamp: str | None
    last_timestamp: str | None
    dataset_checksum: str | None
    parquet_checksum: str | None
    retrieval_count: int
    issues: tuple[IntegrityIssue, ...]
    quality_report: QualityReport | None
    candles: tuple[Candle, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "valid": self.valid,
            "snapshot_path": str(self.snapshot_path),
            "dataset_id": self.dataset_id,
            "provider": self.provider,
            "instrument": self.instrument,
            "timeframe": self.timeframe,
            "row_count": self.row_count,
            "first_timestamp": self.first_timestamp,
            "last_timestamp": self.last_timestamp,
            "dataset_checksum": self.dataset_checksum,
            "parquet_checksum": self.parquet_checksum,
            "retrieval_count": self.retrieval_count,
            "issues": [asdict(issue) for issue in self.issues],
            "quality": self.quality_report.to_dict() if self.quality_report else None,
        }


def _read_json(path: Path, issues: list[IntegrityIssue], code: str) -> dict[str, object] | None:
    if not path.exists():
        issues.append(IntegrityIssue("error", f"missing_{code}", f"required file is missing: {path}"))
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError("root value must be an object")
        return value
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        issues.append(IntegrityIssue("error", f"invalid_{code}", f"cannot read {path}: {exc}"))
        return None


def _resolve_snapshot(path: Path, issues: list[IntegrityIssue]) -> tuple[Path, dict[str, object] | None]:
    index_path = path / "index.json"
    if index_path.exists():
        index = _read_json(index_path, issues, "index")
        if index is None or not isinstance(index.get("latest_dataset_id"), str):
            issues.append(IntegrityIssue("error", "missing_latest_snapshot", "index has no latest_dataset_id"))
            return path, index
        return path / "snapshots" / str(index["latest_dataset_id"]), index
    return path, None


def _retrieval_count(snapshot: Path, dataset_id: str | None) -> int:
    if dataset_id is None or snapshot.parent.name != "snapshots":
        return 0
    retrievals = snapshot.parent.parent / "retrievals"
    count = 0
    for path in retrievals.glob("*.json") if retrievals.exists() else ():
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
            count += record.get("dataset_id") == dataset_id
        except (OSError, json.JSONDecodeError):
            continue
    return count


def verify_dataset(path: str | Path) -> IntegrityReport:
    """Verify a dataset root or a specific immutable snapshot directory."""

    requested = Path(path)
    issues: list[IntegrityIssue] = []
    snapshot, index = _resolve_snapshot(requested, issues)
    manifest = _read_json(snapshot / "manifest.json", issues, "manifest")
    parquet_path = snapshot / "candles.parquet"
    if not parquet_path.exists():
        issues.append(IntegrityIssue("error", "missing_parquet", f"required file is missing: {parquet_path}"))

    dataset_id = str(manifest["dataset_id"]) if manifest and isinstance(manifest.get("dataset_id"), str) else None
    provider = str(manifest["provider"]) if manifest and isinstance(manifest.get("provider"), str) else None
    symbol = str(manifest["instrument"]) if manifest and isinstance(manifest.get("instrument"), str) else None
    timeframe = str(manifest["timeframe"]) if manifest and isinstance(manifest.get("timeframe"), str) else None
    candles: list[Candle] = []
    quality: QualityReport | None = None
    actual_parquet_checksum: str | None = None
    actual_dataset_checksum: str | None = None

    if manifest and manifest.get("schema_version") != SCHEMA_VERSION:
        issues.append(IntegrityIssue("error", "schema_version_mismatch", "manifest schema version is unsupported"))
    if manifest and snapshot.name != dataset_id:
        issues.append(IntegrityIssue("error", "snapshot_name_mismatch", "snapshot directory does not match dataset_id"))
    if index and dataset_id:
        if index.get("latest_dataset_id") != dataset_id:
            issues.append(IntegrityIssue("error", "index_latest_mismatch", "index points to a different dataset"))
        if dataset_id not in index.get("snapshot_ids", []):
            issues.append(IntegrityIssue("error", "index_snapshot_missing", "latest dataset is absent from snapshot_ids"))
        for field, manifest_value in (
            ("provider", provider),
            ("instrument", symbol),
            ("timeframe", timeframe),
        ):
            if index.get(field) != manifest_value:
                issues.append(IntegrityIssue(
                    "error", f"index_{field}_mismatch", f"index {field} differs from snapshot manifest"
                ))

    instrument: Instrument | None = None
    if manifest:
        try:
            instrument = Instrument(
                symbol=str(manifest["instrument"]),
                base_currency=str(manifest["base_currency"]),
                quote_currency=str(manifest["quote_currency"]),
                pip_size=Decimal(str(manifest["pip_size"])),
                price_precision=int(manifest["price_precision"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            issues.append(IntegrityIssue("error", "invalid_instrument_metadata", str(exc)))

    if parquet_path.exists():
        try:
            payload = parquet_path.read_bytes()
            actual_parquet_checksum = checksum_bytes(payload)
            if manifest and manifest.get("parquet_sha256") != actual_parquet_checksum:
                issues.append(IntegrityIssue("error", "parquet_checksum_mismatch", "Parquet SHA-256 does not match manifest"))
            table = pq.read_table(parquet_path)
            if instrument and not table.schema.equals(parquet_schema(instrument.price_precision)):
                issues.append(IntegrityIssue("error", "parquet_schema_mismatch", "Parquet schema does not match canonical schema"))
            if instrument:
                for row in table.to_pylist():
                    if row.get("symbol") != instrument.symbol:
                        issues.append(IntegrityIssue("error", "row_instrument_mismatch", "Parquet row symbol differs from manifest"))
                    candles.append(Candle(
                        instrument=instrument,
                        timestamp=row["timestamp"].astimezone(timezone.utc),
                        timeframe=row["timeframe"],
                        **{name: Decimal(row[name]) for name in PRICE_COLUMNS},
                        source=row["source"],
                        dataset_version=row["dataset_version"],
                        is_synthetic=row["is_synthetic"],
                    ))
        except (OSError, KeyError, TypeError, ValueError, pa.ArrowException) as exc:
            issues.append(IntegrityIssue("error", "corrupt_parquet", f"cannot read canonical candles: {exc}"))

    if instrument and timeframe is not None and candles:
        quality = validate_candles(candles)
        if not quality.valid:
            issues.append(IntegrityIssue("error", "candle_validation_failed", "stored candles fail canonical validation"))
        actual_dataset_checksum = canonical_dataset_checksum(candles)
        actual_id = dataset_identifier(candles, instrument, timeframe)
        checks = (
            ("dataset_checksum_mismatch", manifest.get("dataset_sha256") if manifest else None, actual_dataset_checksum),
            ("dataset_id_mismatch", dataset_id, actual_id),
            ("row_count_mismatch", manifest.get("row_count") if manifest else None, len(candles)),
            ("first_timestamp_mismatch", manifest.get("first_timestamp") if manifest else None, quality.first_timestamp),
            ("last_timestamp_mismatch", manifest.get("last_timestamp") if manifest else None, quality.last_timestamp),
            ("quality_manifest_mismatch", manifest.get("quality") if manifest else None, quality.to_dict()),
        )
        for code, expected, actual in checks:
            if expected != actual:
                issues.append(IntegrityIssue("error", code, f"manifest value does not match stored content"))
    elif parquet_path.exists() and not candles:
        issues.append(IntegrityIssue("error", "empty_or_unreadable_dataset", "snapshot contains no readable candles"))

    valid = not any(issue.severity == "error" for issue in issues)
    return IntegrityReport(
        valid=valid,
        snapshot_path=snapshot,
        dataset_id=dataset_id,
        provider=provider,
        instrument=symbol,
        timeframe=timeframe,
        row_count=len(candles) if candles else None,
        first_timestamp=quality.first_timestamp if quality else None,
        last_timestamp=quality.last_timestamp if quality else None,
        dataset_checksum=actual_dataset_checksum,
        parquet_checksum=actual_parquet_checksum,
        retrieval_count=_retrieval_count(snapshot, dataset_id),
        issues=tuple(issues),
        quality_report=quality,
        candles=tuple(candles),
    )

