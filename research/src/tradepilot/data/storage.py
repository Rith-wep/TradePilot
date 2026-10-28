"""Immutable, content-addressed Parquet snapshots for historical datasets."""

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Sequence

import pyarrow as pa
import pyarrow.parquet as pq

from tradepilot.data.models import Candle, Instrument
from tradepilot.data.validation import QualityReport, validate_candles


SCHEMA_VERSION = "tradepilot-candles-v1"
PRICE_COLUMNS = (
    "bid_open", "bid_high", "bid_low", "bid_close",
    "ask_open", "ask_high", "ask_low", "ask_close",
)


class StorageError(RuntimeError):
    """Raised when a dataset cannot be safely persisted or loaded."""


@dataclass(frozen=True, slots=True)
class CandleRevision:
    timestamp: datetime
    previous_sha256: str
    current_sha256: str


@dataclass(frozen=True, slots=True)
class StoredDataset:
    parquet_path: Path
    manifest_path: Path
    row_count: int
    dataset_checksum: str
    file_checksum: str
    quality_report: QualityReport
    dataset_id: str
    snapshot_path: Path
    revisions: tuple[CandleRevision, ...] = ()


def parquet_schema(precision: int) -> pa.Schema:
    decimal_type = pa.decimal128(max(precision + 7, 12), precision)
    return pa.schema([
        pa.field("timestamp", pa.timestamp("us", tz="UTC"), nullable=False),
        pa.field("symbol", pa.string(), nullable=False),
        pa.field("timeframe", pa.string(), nullable=False),
        *(pa.field(name, decimal_type, nullable=False) for name in PRICE_COLUMNS),
        pa.field("source", pa.string(), nullable=False),
        pa.field("dataset_version", pa.string(), nullable=False),
        pa.field("is_synthetic", pa.bool_(), nullable=False),
    ])


def checksum_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def candle_content_bytes(candle: Candle) -> bytes:
    price_format = f".{candle.instrument.price_precision}f"
    values = [
        candle.timestamp.astimezone(timezone.utc).isoformat(timespec="microseconds"),
        candle.instrument.symbol,
        candle.timeframe,
        *(format(getattr(candle, name), price_format) for name in PRICE_COLUMNS),
        str(candle.is_synthetic).lower(),
    ]
    return "|".join(values).encode("utf-8")


def canonical_content_bytes(candles: Sequence[Candle]) -> bytes:
    ordered = sorted(candles, key=lambda candle: candle.timestamp)
    return b"\n".join(candle_content_bytes(candle) for candle in ordered) + (b"\n" if ordered else b"")


def canonical_dataset_checksum(candles: Sequence[Candle]) -> str:
    return checksum_bytes(canonical_content_bytes(candles))


def schema_identity(instrument: Instrument, timeframe: str) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "instrument": instrument.symbol,
        "base_currency": instrument.base_currency,
        "quote_currency": instrument.quote_currency,
        "pip_size": format(instrument.pip_size, "f"),
        "price_precision": instrument.price_precision,
        "timeframe": timeframe,
        "timestamp_convention": "UTC candle open",
        "price_basis": "bid_ask",
    }


def dataset_identifier(candles: Sequence[Candle], instrument: Instrument, timeframe: str) -> str:
    schema = json.dumps(schema_identity(instrument, timeframe), sort_keys=True, separators=(",", ":"))
    return checksum_bytes(schema.encode("utf-8") + b"\n" + canonical_content_bytes(candles))


def _rows(candles: Sequence[Candle], instrument: Instrument) -> list[dict[str, object]]:
    return [{
        "timestamp": candle.timestamp,
        "symbol": instrument.symbol,
        "timeframe": candle.timeframe,
        **{name: getattr(candle, name) for name in PRICE_COLUMNS},
        "source": candle.source,
        "dataset_version": candle.dataset_version,
        "is_synthetic": candle.is_synthetic,
    } for candle in candles]


def _atomic_json(path: Path, payload: dict[str, object]) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


class ParquetDatasetStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def dataset_directory(self, provider: str, instrument: Instrument, timeframe: str) -> Path:
        return self.root / provider / instrument.symbol / timeframe

    def snapshot_directory(
        self, provider: str, instrument: Instrument, timeframe: str, dataset_id: str
    ) -> Path:
        return self.dataset_directory(provider, instrument, timeframe) / "snapshots" / dataset_id

    def _read_index(self, provider: str, instrument: Instrument, timeframe: str) -> dict[str, object] | None:
        path = self.dataset_directory(provider, instrument, timeframe) / "index.json"
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise StorageError(f"cannot read dataset index {path}: {exc}") from exc

    def latest_dataset_id(self, provider: str, instrument: Instrument, timeframe: str) -> str | None:
        index = self._read_index(provider, instrument, timeframe)
        return str(index["latest_dataset_id"]) if index else None

    def load_snapshot(
        self, provider: str, instrument: Instrument, timeframe: str, dataset_id: str
    ) -> list[Candle]:
        path = self.snapshot_directory(provider, instrument, timeframe, dataset_id) / "candles.parquet"
        if not path.exists():
            raise StorageError(f"snapshot Parquet file does not exist: {path}")
        try:
            rows = pq.read_table(path).to_pylist()
            return [
                Candle(
                    instrument=instrument,
                    timestamp=row["timestamp"].astimezone(timezone.utc),
                    timeframe=row["timeframe"],
                    **{name: Decimal(row[name]) for name in PRICE_COLUMNS},
                    source=row["source"],
                    dataset_version=row["dataset_version"],
                    is_synthetic=row["is_synthetic"],
                )
                for row in rows
            ]
        except (OSError, KeyError, TypeError, ValueError, pa.ArrowException) as exc:
            raise StorageError(f"cannot load dataset {path}: {exc}") from exc

    def load(self, provider: str, instrument: Instrument, timeframe: str) -> list[Candle]:
        dataset_id = self.latest_dataset_id(provider, instrument, timeframe)
        return [] if dataset_id is None else self.load_snapshot(provider, instrument, timeframe, dataset_id)

    def compare_snapshots(
        self,
        provider: str,
        instrument: Instrument,
        timeframe: str,
        previous_id: str,
        current_id: str,
    ) -> tuple[CandleRevision, ...]:
        previous = {item.timestamp: item for item in self.load_snapshot(provider, instrument, timeframe, previous_id)}
        current = {item.timestamp: item for item in self.load_snapshot(provider, instrument, timeframe, current_id)}
        return tuple(
            CandleRevision(
                timestamp,
                checksum_bytes(candle_content_bytes(previous[timestamp])),
                checksum_bytes(candle_content_bytes(current[timestamp])),
            )
            for timestamp in sorted(previous.keys() & current.keys())
            if candle_content_bytes(previous[timestamp]) != candle_content_bytes(current[timestamp])
        )

    def _record_retrieval(
        self,
        directory: Path,
        dataset_id: str,
        retrieved_at: datetime,
        request_start: datetime,
        request_end: datetime,
        provider_metadata: dict[str, str],
    ) -> None:
        payload: dict[str, object] = {
            "dataset_id": dataset_id,
            "retrieved_at": retrieved_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            "request_start": request_start.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            "request_end": request_end.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            "provider_metadata": dict(sorted(provider_metadata.items())),
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        retrievals = directory / "retrievals"
        retrievals.mkdir(parents=True, exist_ok=True)
        path = retrievals / f"{checksum_bytes(encoded)}.json"
        if not path.exists():
            _atomic_json(path, payload)

    def save(
        self,
        provider: str,
        instrument: Instrument,
        timeframe: str,
        candles: Sequence[Candle],
        *,
        retrieved_at: datetime,
        request_start: datetime,
        request_end: datetime,
        provider_metadata: dict[str, str] | None = None,
        allow_revisions: bool = False,
    ) -> StoredDataset:
        previous_id = self.latest_dataset_id(provider, instrument, timeframe)
        existing = [] if previous_id is None else self.load_snapshot(provider, instrument, timeframe, previous_id)
        merged_by_timestamp = {candle.timestamp: candle for candle in existing}
        revisions: list[CandleRevision] = []
        for candle in candles:
            prior = merged_by_timestamp.get(candle.timestamp)
            if prior is not None and candle_content_bytes(prior) != candle_content_bytes(candle):
                if not allow_revisions:
                    raise StorageError(f"conflicting candle already stored at {candle.timestamp.isoformat()}")
                revisions.append(CandleRevision(
                    candle.timestamp,
                    checksum_bytes(candle_content_bytes(prior)),
                    checksum_bytes(candle_content_bytes(candle)),
                ))
            merged_by_timestamp[candle.timestamp] = candle
        merged = sorted(merged_by_timestamp.values(), key=lambda candle: candle.timestamp)
        report = validate_candles(merged)
        if not report.valid:
            raise StorageError("refusing to save a dataset with validation errors")

        dataset_checksum = canonical_dataset_checksum(merged)
        dataset_id = dataset_identifier(merged, instrument, timeframe)
        directory = self.dataset_directory(provider, instrument, timeframe)
        snapshot = self.snapshot_directory(provider, instrument, timeframe, dataset_id)
        parquet_path = snapshot / "candles.parquet"
        manifest_path = snapshot / "manifest.json"
        if snapshot.exists() and (not parquet_path.exists() or not manifest_path.exists()):
            raise StorageError(f"existing snapshot is incomplete: {snapshot}")
        if not snapshot.exists():
            snapshot.mkdir(parents=True)
            parquet_temp = snapshot / ".candles.parquet.tmp"
            table = pa.Table.from_pylist(_rows(merged, instrument), schema=parquet_schema(instrument.price_precision))
            pq.write_table(table, parquet_temp, compression="zstd")
            file_checksum = checksum_bytes(parquet_temp.read_bytes())
            manifest: dict[str, object] = {
                **schema_identity(instrument, timeframe),
                "dataset_id": dataset_id,
                "dataset_sha256": dataset_checksum,
                "parquet_sha256": file_checksum,
                "provider": provider,
                "row_count": len(merged),
                "first_timestamp": report.first_timestamp,
                "last_timestamp": report.last_timestamp,
                "quality": report.to_dict(),
            }
            os.replace(parquet_temp, parquet_path)
            _atomic_json(manifest_path, manifest)
        else:
            file_checksum = checksum_bytes(parquet_path.read_bytes())

        directory.mkdir(parents=True, exist_ok=True)
        self._record_retrieval(
            directory, dataset_id, retrieved_at, request_start, request_end, provider_metadata or {}
        )
        index = self._read_index(provider, instrument, timeframe) or {
            "schema_version": SCHEMA_VERSION,
            "provider": provider,
            "instrument": instrument.symbol,
            "timeframe": timeframe,
            "snapshot_ids": [],
        }
        snapshot_ids = list(index.get("snapshot_ids", []))
        if dataset_id not in snapshot_ids:
            snapshot_ids.append(dataset_id)
        index["snapshot_ids"] = snapshot_ids
        index["latest_dataset_id"] = dataset_id
        _atomic_json(directory / "index.json", index)
        return StoredDataset(
            parquet_path, manifest_path, len(merged), dataset_checksum, file_checksum,
            report, dataset_id, snapshot, tuple(revisions),
        )
