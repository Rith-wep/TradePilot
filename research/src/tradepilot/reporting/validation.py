"""Research-level provenance, timestamp, and duplicate validation."""

import os
import subprocess
from dataclasses import asdict, is_dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Mapping, Sequence

from tradepilot.data.integrity import IntegrityReport
from tradepilot.indicators.models import PriceBasis
from tradepilot.reporting.models import (
    REPORT_SCHEMA_VERSION,
    RESEARCH_ENGINE_VERSION,
    ConfigurationValue,
    IndicatorParameter,
    ReportedSignal,
    ResearchContent,
    ResearchRun,
)
from tradepilot.strategies.models import SetupRecord
from tradepilot.strategies.base import configuration_fingerprint as calculate_configuration_fingerprint


class ReportValidationError(ValueError):
    """Raised when candidate report provenance or content is inconsistent."""


def resolve_implementation_revision(cwd: str | Path | None = None) -> str:
    override = os.environ.get("TRADEPILOT_IMPLEMENTATION_REVISION", "").strip()
    if override:
        return override
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=cwd, capture_output=True,
            text=True, check=True, timeout=2,
        )
        revision = result.stdout.strip()
        return revision or "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def configuration_values(configuration: object) -> tuple[ConfigurationValue, ...]:
    if is_dataclass(configuration):
        source = asdict(configuration)
    elif isinstance(configuration, Mapping):
        source = dict(configuration)
    else:
        raise ReportValidationError("strategy configuration must be a dataclass or mapping")
    values = []
    for name, value in sorted(source.items()):
        if not (value is None or isinstance(value, (Decimal, str, int, bool))):
            raise ReportValidationError(f"unsupported configuration value: {name}")
        if isinstance(value, Decimal) and not value.is_finite():
            raise ReportValidationError(f"configuration Decimal must be finite: {name}")
        values.append(ConfigurationValue(name, value))
    return tuple(values)


def _validate_sha256(name: str, value: str | None) -> str:
    if value is None or len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ReportValidationError(f"{name} must be a lowercase SHA-256 value")
    return value


def _timeframe_duration(timeframe: str) -> timedelta:
    if timeframe == "H1":
        return timedelta(hours=1)
    raise ReportValidationError(f"unsupported timeframe duration: {timeframe}")


def build_research_run(
    integrity: IntegrityReport,
    *,
    strategy_name: str,
    strategy_version: str,
    configuration_fingerprint: str,
    strategy_configuration: object,
    indicator_parameters: Sequence[IndicatorParameter],
    session_calendar_id: str,
    reject_unexpected_gaps: bool,
    setups: Sequence[SetupRecord],
    created_at: datetime,
    implementation_revision: str,
) -> ResearchRun:
    if not integrity.valid:
        raise ReportValidationError("dataset integrity report must be valid")
    dataset_id = _validate_sha256("dataset_id", integrity.dataset_id)
    checksum = _validate_sha256("dataset_checksum", integrity.dataset_checksum)
    _validate_sha256("configuration_fingerprint", configuration_fingerprint)
    expected_fingerprint = calculate_configuration_fingerprint(
        strategy_name, strategy_version, strategy_configuration, session_calendar_id
    )
    if configuration_fingerprint != expected_fingerprint:
        raise ReportValidationError("configuration fingerprint does not match strategy configuration")
    if created_at.tzinfo is None or created_at.utcoffset() is None:
        raise ReportValidationError("run creation timestamp must be timezone-aware")
    if not implementation_revision.strip():
        raise ReportValidationError("implementation_revision must not be empty")
    if not integrity.candles or integrity.instrument is None or integrity.timeframe is None:
        raise ReportValidationError("verified dataset must contain candles and provenance")
    duration = _timeframe_duration(integrity.timeframe)
    candle_timestamps = {candle.timestamp for candle in integrity.candles}
    seen: set[tuple[object, ...]] = set()
    ordered_setups = sorted(setups, key=lambda item: (item.detection_candle_open_time, item.direction.value))
    reported: list[ReportedSignal] = []
    for setup in ordered_setups:
        if setup.identity_key in seen:
            raise ReportValidationError(f"duplicate setup identity: {setup.identity_key}")
        seen.add(setup.identity_key)
        if setup.strategy_name != strategy_name or setup.strategy_version != strategy_version:
            raise ReportValidationError("setup strategy provenance does not match research run")
        if setup.configuration_fingerprint != configuration_fingerprint:
            raise ReportValidationError("setup configuration fingerprint does not match research run")
        if setup.instrument != integrity.instrument or setup.timeframe != integrity.timeframe:
            raise ReportValidationError("setup dataset provenance does not match selected dataset")
        if (
            setup.detection_candle_open_time.tzinfo is None
            or setup.detection_candle_open_time.utcoffset() != timedelta(0)
            or setup.observable_at.tzinfo is None
            or setup.observable_at.utcoffset() != timedelta(0)
        ):
            raise ReportValidationError("setup timestamps must be explicitly UTC")
        if setup.detection_candle_open_time not in candle_timestamps:
            raise ReportValidationError("setup detection timestamp is absent from selected dataset")
        if setup.observable_at != setup.detection_candle_open_time + duration:
            raise ReportValidationError("setup observable timestamp does not equal completed-candle time")
        reported.append(ReportedSignal(dataset_id, checksum, setup))
    parameters = tuple(indicator_parameters)
    for parameter in parameters:
        if parameter.period <= 0 or parameter.price_basis not in ("bid", "ask", "mid"):
            raise ReportValidationError("indicator parameters are invalid")
    content = ResearchContent(
        schema_version=REPORT_SCHEMA_VERSION,
        dataset_id=dataset_id,
        dataset_checksum=checksum,
        instrument=integrity.instrument,
        timeframe=integrity.timeframe,
        dataset_first_timestamp=integrity.candles[0].timestamp,
        dataset_last_timestamp=integrity.candles[-1].timestamp,
        strategy_name=strategy_name,
        strategy_version=strategy_version,
        configuration_fingerprint=configuration_fingerprint,
        strategy_configuration=configuration_values(strategy_configuration),
        indicator_parameters=parameters,
        session_calendar_id=session_calendar_id,
        reject_unexpected_gaps=reject_unexpected_gaps,
        research_engine_version=RESEARCH_ENGINE_VERSION,
        implementation_revision=implementation_revision,
        signals=tuple(reported),
    )
    return ResearchRun(content, created_at.astimezone(timezone.utc))
