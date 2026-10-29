"""Deterministic real-data quality and research-readiness evidence."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from math import ceil
from statistics import median
from typing import Sequence

from tradepilot.data.integrity import IntegrityReport
from tradepilot.data.sessions import TradingSessionCalendar, classify_gaps
from tradepilot.data.storage import CandleRevision
from tradepilot.reporting.canonical import canonical_json_bytes, sha256_hex


READINESS_SCHEMA_VERSION = "tradepilot-real-data-readiness/v1"


class ReadinessStatus(str, Enum):
    READY = "READY"
    FAILED = "FAILED"


@dataclass(frozen=True, slots=True)
class ReadinessPolicy:
    minimum_candles: int = 200
    minimum_coverage: Decimal = Decimal("0.99")
    unusual_spread_pips: Decimal = Decimal("20")
    reject_unexpected_gaps: bool = True
    require_oanda_real_data: bool = True
    version: str = "real-data-readiness-policy/v1"

    def __post_init__(self) -> None:
        if self.minimum_candles <= 0:
            raise ValueError("minimum_candles must be positive")
        if not Decimal(0) < self.minimum_coverage <= Decimal(1):
            raise ValueError("minimum_coverage must be in (0, 1]")
        if self.unusual_spread_pips <= 0:
            raise ValueError("unusual_spread_pips must be positive")


@dataclass(frozen=True, slots=True)
class ReadinessIssue:
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class CoverageAudit:
    requested_start: datetime
    requested_end: datetime
    expected_open_candles: int
    observed_expected_candles: int
    total_rows: int
    coverage_ratio: Decimal
    boundary_missing_count: int


@dataclass(frozen=True, slots=True)
class SpreadAudit:
    observation_count: int
    minimum_pips: Decimal | None
    median_pips: Decimal | None
    percentile_95_pips: Decimal | None
    maximum_pips: Decimal | None
    unusual_count: int


@dataclass(frozen=True, slots=True)
class RevisionAudit:
    previous_dataset_id: str | None
    current_dataset_id: str | None
    revision_count: int
    approved: bool
    timestamps: tuple[datetime, ...]


@dataclass(frozen=True, slots=True)
class PipelineEvidence:
    strategy_name: str
    strategy_version: str
    configuration_fingerprint: str
    candidate_report_id: str
    signal_count: int
    repeated_report_id: str
    reproducible: bool


@dataclass(frozen=True, slots=True)
class ReadinessContent:
    schema_version: str
    status: ReadinessStatus
    dataset_id: str | None
    dataset_checksum: str | None
    provider: str | None
    instrument: str | None
    timeframe: str | None
    calendar_id: str
    policy: ReadinessPolicy
    coverage: CoverageAudit
    expected_closure_count: int
    unexpected_missing_count: int
    spread: SpreadAudit
    revisions: RevisionAudit
    integrity_valid: bool
    pipeline: tuple[PipelineEvidence, ...]
    issues: tuple[ReadinessIssue, ...]


@dataclass(frozen=True, slots=True)
class ReadinessReport:
    report_id: str
    content: ReadinessContent


def _expected_timestamps(start: datetime, end: datetime, calendar: TradingSessionCalendar) -> set[datetime]:
    expected: set[datetime] = set()
    current = start
    while current < end:
        if calendar.is_expected_open(current):
            expected.add(current)
        current += timedelta(hours=1)
    return expected


def _spread_audit(integrity: IntegrityReport, threshold: Decimal) -> SpreadAudit:
    values: list[Decimal] = []
    for candle in integrity.candles:
        for bid, ask in zip(
            (candle.bid_open, candle.bid_high, candle.bid_low, candle.bid_close),
            (candle.ask_open, candle.ask_high, candle.ask_low, candle.ask_close),
        ):
            values.append((ask - bid) / candle.instrument.pip_size)
    if not values:
        return SpreadAudit(0, None, None, None, None, 0)
    ordered = sorted(values)
    p95 = ordered[max(0, ceil(Decimal("0.95") * len(ordered)) - 1)]
    return SpreadAudit(
        len(values), ordered[0], median(ordered), p95, ordered[-1],
        sum(value > threshold for value in values),
    )


def build_readiness_report(
    integrity: IntegrityReport,
    *,
    requested_start: datetime,
    requested_end: datetime,
    calendar: TradingSessionCalendar,
    policy: ReadinessPolicy | None = None,
    previous_dataset_id: str | None = None,
    revisions: Sequence[CandleRevision] = (),
    revisions_approved: bool = False,
    pipeline: Sequence[PipelineEvidence] = (),
    pipeline_required: bool = False,
) -> ReadinessReport:
    policy = policy or ReadinessPolicy()
    if requested_start.tzinfo is None or requested_start.utcoffset() != timedelta(0):
        raise ValueError("requested_start must be UTC")
    if requested_end.tzinfo is None or requested_end.utcoffset() != timedelta(0) or requested_start >= requested_end:
        raise ValueError("requested_end must form a valid UTC range")
    expected = _expected_timestamps(requested_start, requested_end, calendar)
    observed = {item.timestamp for item in integrity.candles if requested_start <= item.timestamp < requested_end}
    observed_expected = observed & expected
    ratio = Decimal(len(observed_expected)) / Decimal(len(expected)) if expected else Decimal(0)
    boundary_missing = len(expected - observed)
    coverage = CoverageAudit(
        requested_start, requested_end, len(expected), len(observed_expected),
        len(integrity.candles), ratio, boundary_missing,
    )
    gaps = classify_gaps(integrity.candles, calendar)
    revision_values = tuple(revisions)
    revision_audit = RevisionAudit(
        previous_dataset_id, integrity.dataset_id, len(revision_values), revisions_approved,
        tuple(item.timestamp for item in revision_values),
    )
    issues: list[ReadinessIssue] = []
    if not integrity.valid:
        issues.append(ReadinessIssue("BAD_INTEGRITY", "immutable snapshot integrity verification failed"))
    if policy.require_oanda_real_data and (
        integrity.provider != "oanda-v20" or any(item.is_synthetic for item in integrity.candles)
    ):
        issues.append(ReadinessIssue("INCOMPATIBLE_PROVIDER", "readiness requires non-synthetic OANDA data"))
    if integrity.timeframe != "H1" or integrity.instrument not in ("EURUSD", "GBPUSD"):
        issues.append(ReadinessIssue("INCOMPATIBLE_DATA", "only EURUSD and GBPUSD H1 are supported"))
    if len(integrity.candles) < policy.minimum_candles:
        issues.append(ReadinessIssue("INSUFFICIENT_CANDLES", "dataset has fewer candles than the readiness minimum"))
    if ratio < policy.minimum_coverage:
        issues.append(ReadinessIssue("INSUFFICIENT_COVERAGE", "expected-session coverage is below policy"))
    if policy.reject_unexpected_gaps and gaps.unexpected_missing_count:
        issues.append(ReadinessIssue("UNEXPECTED_GAPS", "open-session candle intervals are missing"))
    if revision_values and not revisions_approved:
        issues.append(ReadinessIssue("UNAPPROVED_REVISIONS", "historical candle revisions require explicit approval"))
    evidence = tuple(pipeline)
    if pipeline_required and not evidence:
        issues.append(ReadinessIssue("PIPELINE_NOT_VERIFIED", "research pipeline evidence is required"))
    if any(not item.reproducible for item in evidence):
        issues.append(ReadinessIssue("PIPELINE_NOT_REPRODUCIBLE", "candidate report identity changed on repetition"))
    content = ReadinessContent(
        READINESS_SCHEMA_VERSION, ReadinessStatus.FAILED if issues else ReadinessStatus.READY,
        integrity.dataset_id, integrity.dataset_checksum, integrity.provider,
        integrity.instrument, integrity.timeframe, calendar.calendar_id, policy,
        coverage, gaps.expected_closure_count, gaps.unexpected_missing_count,
        _spread_audit(integrity, policy.unusual_spread_pips), revision_audit,
        integrity.valid, evidence, tuple(issues),
    )
    return ReadinessReport(sha256_hex(canonical_json_bytes(content)), content)
