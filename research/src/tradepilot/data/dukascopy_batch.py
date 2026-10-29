"""Manifest-driven, preflight-first Dukascopy multi-month consolidation."""

import json
import os
import uuid
from dataclasses import dataclass, replace
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from math import ceil
from pathlib import Path
from statistics import median

from tradepilot.data.integrity import IntegrityReport, verify_dataset
from tradepilot.data.models import Candle, Instrument
from tradepilot.data.normalization import normalize_provider_candle
from tradepilot.data.providers.dukascopy_csv import DukascopyCsvError, DukascopyCsvMarketDataProvider
from tradepilot.data.sessions import WeeklySessionCalendar
from tradepilot.data.source_artifacts import (
    SOURCE_ARTIFACT_SCHEMA_VERSION, SourceArtifact, SourceArtifactManifest,
)
from tradepilot.data.storage import ParquetDatasetStore, StoredDataset
from tradepilot.data.validation import validate_candles
from tradepilot.reporting.canonical import canonical_json_bytes, sha256_hex


BATCH_PLAN_VERSION = "tradepilot-dukascopy-batch-plan/v1"
BATCH_QUALITY_VERSION = "tradepilot-dukascopy-batch-quality/v1"
INSTRUMENTS = {
    "EURUSD": Instrument("EURUSD", "EUR", "USD", Decimal("0.0001"), 5),
    "GBPUSD": Instrument("GBPUSD", "GBP", "USD", Decimal("0.0001"), 5),
}


class DukascopyBatchError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class MonthlySource:
    month: str
    bid_path: Path
    ask_path: Path
    bid_sha256: str
    ask_sha256: str


@dataclass(frozen=True, slots=True)
class BatchPlan:
    source_path: Path
    instrument: Instrument
    timeframe: str
    timestamp_format: str
    delimiter: str
    calendar: WeeklySessionCalendar
    months: tuple[MonthlySource, ...]
    plan_sha256: str


@dataclass(frozen=True, slots=True)
class PeriodQuality:
    period: str
    row_count: int
    expected_open_count: int
    missing_open_count: int
    coverage_ratio: Decimal
    minimum_spread_pips: Decimal | None
    median_spread_pips: Decimal | None
    percentile_95_spread_pips: Decimal | None
    maximum_spread_pips: Decimal | None


@dataclass(frozen=True, slots=True)
class BatchQualityReport:
    schema_version: str
    instrument: str
    timeframe: str
    dataset_id: str
    dataset_checksum: str
    source_artifacts_checksum: str
    monthly: tuple[PeriodQuality, ...]
    yearly: tuple[PeriodQuality, ...]
    duplicate_count: int
    overlap_count: int
    revision_count: int

    @property
    def report_id(self) -> str:
        return sha256_hex(canonical_json_bytes(self))


@dataclass(frozen=True, slots=True)
class BatchImportResult:
    stored: StoredDataset
    integrity: IntegrityReport
    artifacts: SourceArtifactManifest
    quality: BatchQualityReport


def _month_start(value: str) -> datetime:
    try:
        parsed = datetime.strptime(value, "%Y-%m").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise DukascopyBatchError(f"invalid month: {value}") from exc
    return parsed


def _next_month(value: datetime) -> datetime:
    return datetime(value.year + (value.month == 12), 1 if value.month == 12 else value.month + 1, 1, tzinfo=timezone.utc)


def load_batch_plan(path: str | Path) -> BatchPlan:
    source = Path(path)
    try:
        raw_bytes = source.read_bytes()
        payload = json.loads(raw_bytes.decode("utf-8"))
        if payload.get("schema_version") != BATCH_PLAN_VERSION:
            raise DukascopyBatchError("unsupported batch plan schema")
        instrument = INSTRUMENTS[payload["instrument"]]
        if payload.get("timeframe") != "H1":
            raise DukascopyBatchError("batch plan timeframe must be H1")
        timestamp_format = payload["timestamp_format"]
        delimiter = payload["delimiter"]
        calendar_data = payload["calendar"]
        calendar = WeeklySessionCalendar(
            timezone_name=calendar_data["timezone"],
            open_weekday=int(calendar_data["open_weekday"]),
            open_time=time.fromisoformat(calendar_data["open_time"]),
            close_weekday=int(calendar_data["close_weekday"]),
            close_time=time.fromisoformat(calendar_data["close_time"]),
            closure_dates=frozenset(date.fromisoformat(item) for item in calendar_data.get("closure_dates", [])),
            name=calendar_data["name"],
        )
        months = tuple(MonthlySource(
            item["month"], (source.parent / item["bid_path"]).resolve(),
            (source.parent / item["ask_path"]).resolve(), item["bid_sha256"], item["ask_sha256"],
        ) for item in payload["months"])
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, DukascopyBatchError):
            raise
        raise DukascopyBatchError(f"invalid batch plan: {exc}") from exc
    if not months:
        raise DukascopyBatchError("batch plan must contain monthly sources")
    starts = tuple(_month_start(item.month) for item in months)
    if starts != tuple(sorted(starts)) or len(set(starts)) != len(starts):
        raise DukascopyBatchError("batch months must be unique and chronological")
    if any(current != _next_month(previous) for previous, current in zip(starts, starts[1:])):
        raise DukascopyBatchError("batch months must be contiguous")
    return BatchPlan(
        source, instrument, "H1", timestamp_format, delimiter, calendar, months,
        sha256_hex(canonical_json_bytes(payload)),
    )


def _expected(start: datetime, end: datetime, calendar: WeeklySessionCalendar) -> set[datetime]:
    output = set()
    current = start
    while current < end:
        if calendar.is_expected_open(current):
            output.add(current)
        current += timedelta(hours=1)
    return output


def _period_quality(label: str, candles: tuple[Candle, ...], start: datetime, end: datetime, calendar) -> PeriodQuality:
    values = tuple(item for item in candles if start <= item.timestamp < end)
    expected = _expected(start, end, calendar)
    observed = {item.timestamp for item in values}
    spreads = sorted(
        (ask - bid) / item.instrument.pip_size
        for item in values
        for bid, ask in zip(
            (item.bid_open, item.bid_high, item.bid_low, item.bid_close),
            (item.ask_open, item.ask_high, item.ask_low, item.ask_close),
        )
    )
    matched = observed & expected
    return PeriodQuality(
        label, len(values), len(expected), len(expected - observed),
        Decimal(len(matched)) / Decimal(len(expected)) if expected else Decimal(0),
        spreads[0] if spreads else None, median(spreads) if spreads else None,
        spreads[max(0, ceil(Decimal("0.95") * len(spreads)) - 1)] if spreads else None,
        spreads[-1] if spreads else None,
    )


def _save_quality(root: Path, quality: BatchQualityReport) -> Path:
    directory = root / "quality-reports"
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{quality.report_id}.json"
    payload = canonical_json_bytes({"report_id": quality.report_id, "content": quality})
    if target.exists():
        if target.read_bytes() != payload:
            raise DukascopyBatchError("existing quality report conflicts with deterministic content")
        return target
    temporary = directory / f".{quality.report_id}-{uuid.uuid4().hex}.tmp"
    temporary.write_bytes(payload)
    try:
        os.link(temporary, target)
    except FileExistsError:
        if target.read_bytes() != payload:
            raise DukascopyBatchError("concurrent quality report conflicts")
    finally:
        temporary.unlink(missing_ok=True)
    return target


def import_batch(
    plan_path: str | Path, store: ParquetDatasetStore, *,
    allow_revisions: bool = False, retrieved_at: datetime | None = None,
) -> BatchImportResult:
    plan = load_batch_plan(plan_path)
    artifacts: list[SourceArtifact] = []
    by_timestamp: dict[datetime, Candle] = {}
    month_ranges: list[tuple[str, datetime, datetime]] = []
    for source in plan.months:
        month_start = _month_start(source.month)
        month_end = _next_month(month_start)
        try:
            provider = DukascopyCsvMarketDataProvider(
                source.bid_path, source.ask_path, timestamp_format=plan.timestamp_format,
                delimiter=plan.delimiter, expected_bid_sha256=source.bid_sha256,
                expected_ask_sha256=source.ask_sha256, instrument_symbol=plan.instrument.symbol,
            )
        except DukascopyCsvError as exc:
            raise DukascopyBatchError(f"month {source.month}: {exc}") from exc
        if any(not month_start <= item.timestamp < month_end for item in provider.candles):
            raise DukascopyBatchError(f"month {source.month} contains a timestamp outside its UTC month")
        normalized = tuple(normalize_provider_candle(
            item, instrument=plan.instrument, provider="dukascopy-csv-batch",
            dataset_version=provider.dataset_version, is_synthetic=False,
        ) for item in provider.candles)
        report = validate_candles(normalized)
        if not report.valid:
            raise DukascopyBatchError(f"month {source.month} failed canonical validation")
        expected = _expected(month_start, month_end, plan.calendar)
        observed = {item.timestamp for item in normalized}
        if expected - observed:
            raise DukascopyBatchError(f"month {source.month} has unexpected open-session gaps")
        if observed - expected:
            raise DukascopyBatchError(f"month {source.month} contains candles during configured closure")
        for candle in normalized:
            if candle.timestamp in by_timestamp:
                raise DukascopyBatchError(f"cross-month overlap at {candle.timestamp.isoformat()}")
            by_timestamp[candle.timestamp] = candle
        for side, path, checksum, rows in (
            ("BID", source.bid_path, provider.bid_sha256, provider.bid_row_count),
            ("ASK", source.ask_path, provider.ask_sha256, provider.ask_row_count),
        ):
            artifacts.append(SourceArtifact(
                source.month, side, path.name, checksum, path.stat().st_size, rows,
                normalized[0].timestamp, normalized[-1].timestamp,
            ))
        month_ranges.append((source.month, month_start, month_end))
    artifact_manifest = SourceArtifactManifest(
        SOURCE_ARTIFACT_SCHEMA_VERSION, plan.instrument.symbol, "H1",
        plan.timestamp_format, plan.delimiter, plan.calendar.calendar_id, tuple(artifacts),
    )
    aggregate_version = f"dukascopy-csv-batch/v1:{artifact_manifest.checksum}"
    candles = tuple(replace(item, dataset_version=aggregate_version) for item in sorted(by_timestamp.values(), key=lambda value: value.timestamp))
    full_report = validate_candles(candles)
    if not full_report.valid:
        raise DukascopyBatchError("consolidated candles failed canonical validation")
    stored = store.save(
        "dukascopy-csv-batch", plan.instrument, "H1", candles,
        retrieved_at=retrieved_at or datetime.now(timezone.utc),
        request_start=month_ranges[0][1], request_end=month_ranges[-1][2],
        provider_metadata={
            "batch_plan_sha256": plan.plan_sha256,
            "source_artifacts_sha256": artifact_manifest.checksum,
            "month_count": str(len(plan.months)),
            "calendar_id": plan.calendar.calendar_id,
        },
        allow_revisions=allow_revisions, source_artifacts=artifact_manifest,
        merge_existing=False,
    )
    integrity = verify_dataset(stored.snapshot_path)
    if not integrity.valid:
        raise DukascopyBatchError("published consolidated snapshot failed integrity verification")
    monthly = tuple(_period_quality(label, candles, start, end, plan.calendar) for label, start, end in month_ranges)
    years = sorted({start.year for _, start, _ in month_ranges})
    yearly = tuple(_period_quality(
        str(year), candles,
        max(datetime(year, 1, 1, tzinfo=timezone.utc), month_ranges[0][1]),
        min(datetime(year + 1, 1, 1, tzinfo=timezone.utc), month_ranges[-1][2]),
        plan.calendar,
    ) for year in years)
    quality = BatchQualityReport(
        BATCH_QUALITY_VERSION, plan.instrument.symbol, "H1", stored.dataset_id,
        stored.dataset_checksum, artifact_manifest.checksum, monthly, yearly, 0, 0,
        len(stored.revisions),
    )
    _save_quality(stored.snapshot_path.parent.parent, quality)
    return BatchImportResult(stored, integrity, artifact_manifest, quality)
