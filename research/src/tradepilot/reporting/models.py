"""Immutable models for deterministic research content and run metadata."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from tradepilot.indicators.models import PriceBasis
from tradepilot.strategies.models import SetupRecord


REPORT_SCHEMA_VERSION = "tradepilot-candidate-report-v1"
RESEARCH_ENGINE_VERSION = "tradepilot-research-report/1.0.0"


@dataclass(frozen=True, slots=True)
class ConfigurationValue:
    name: str
    value: Decimal | str | int | bool | None


@dataclass(frozen=True, slots=True)
class IndicatorParameter:
    name: str
    period: int
    price_basis: PriceBasis


@dataclass(frozen=True, slots=True)
class ReportedSignal:
    dataset_id: str
    dataset_checksum: str
    setup: SetupRecord


@dataclass(frozen=True, slots=True)
class ResearchContent:
    schema_version: str
    dataset_id: str
    dataset_checksum: str
    instrument: str
    timeframe: str
    dataset_first_timestamp: datetime
    dataset_last_timestamp: datetime
    strategy_name: str
    strategy_version: str
    configuration_fingerprint: str
    strategy_configuration: tuple[ConfigurationValue, ...]
    indicator_parameters: tuple[IndicatorParameter, ...]
    session_calendar_id: str
    reject_unexpected_gaps: bool
    research_engine_version: str
    implementation_revision: str
    signals: tuple[ReportedSignal, ...]


@dataclass(frozen=True, slots=True)
class ResearchRun:
    content: ResearchContent
    created_at: datetime


@dataclass(frozen=True, slots=True)
class StoredReport:
    report_id: str
    report_path: Path
    run_metadata_path: Path
    reused: bool


