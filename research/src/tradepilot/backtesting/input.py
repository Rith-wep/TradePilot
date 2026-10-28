"""Verified immutable research-report loading for the execution simulator."""

import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from tradepilot.backtesting.simulation_models import SimulationCandidateReport
from tradepilot.reporting.storage import verify_report
from tradepilot.strategies.models import Direction, NamedValue, RuleEvidence, SetupRecord


class SimulationInputError(ValueError):
    """Raised when immutable simulator input cannot be verified or decoded."""


def _utc(value: object) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise SimulationInputError("report timestamp must be a UTC string ending in Z")
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _setup(value: object) -> SetupRecord:
    if not isinstance(value, dict):
        raise SimulationInputError("reported setup must be an object")
    try:
        named = tuple(NamedValue(str(item["name"]), item.get("value")) for item in value["indicator_values"])
        evidence = tuple(RuleEvidence(
            str(item["rule"]), bool(item["passed"]), item.get("actual"), str(item["expected"])
        ) for item in value["rule_evidence"])
        reference = value.get("structural_invalidation_reference")
        return SetupRecord(
            str(value["strategy_name"]), str(value["strategy_version"]),
            str(value["instrument"]), str(value["timeframe"]),
            _utc(value["detection_candle_open_time"]), _utc(value["observable_at"]),
            Direction(str(value["direction"])), str(value["setup_type"]), named,
            evidence, tuple(str(item) for item in value["invalidation_conditions"]),
            Decimal(str(reference)) if reference is not None else None,
            str(value["configuration_fingerprint"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise SimulationInputError(f"invalid reported setup: {exc}") from exc


def load_verified_candidate_report(path: str | Path) -> SimulationCandidateReport:
    verification = verify_report(path)
    if not verification.valid or verification.report_id is None:
        codes = ", ".join(issue.code for issue in verification.issues)
        raise SimulationInputError(f"research report integrity verification failed: {codes}")
    try:
        envelope = json.loads(verification.report_path.read_text(encoding="utf-8"))
        content = envelope["content"]
        signals = tuple(_setup(item["setup"]) for item in content["signals"])
        return SimulationCandidateReport(
            verification.report_id, str(content["dataset_id"]),
            str(content["dataset_checksum"]), str(content["instrument"]),
            str(content["timeframe"]), str(content["strategy_name"]),
            str(content["strategy_version"]), str(content["configuration_fingerprint"]),
            str(content["session_calendar_id"]), signals,
        )
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise SimulationInputError(f"cannot decode verified research report: {exc}") from exc
