"""Research verification workflow for integrity-verified real-data snapshots."""

from datetime import datetime
from pathlib import Path

from tradepilot.data.integrity import IntegrityReport
from tradepilot.data.readiness import PipelineEvidence
from tradepilot.data.sessions import TradingSessionCalendar
from tradepilot.reporting.storage import ReportStorage, ReportStorageError, report_identifier, verify_report
from tradepilot.reporting.validation import resolve_implementation_revision
from tradepilot.strategies.breakout import BreakoutConfig
from tradepilot.strategies.pullback import PullbackConfig
from tradepilot.workflows.research_run import (
    build_candidate_research_run,
    evaluate_candidate_research,
)


def verify_candidate_pipeline(
    integrity: IntegrityReport,
    calendar: TradingSessionCalendar,
    report_root: str | Path,
    *,
    implementation_revision: str,
    created_at: datetime,
) -> tuple[PipelineEvidence, ...]:
    """Run unchanged default strategies; zero candidates are a valid outcome."""
    configurations = (BreakoutConfig(), PullbackConfig())
    evidence = []
    storage = ReportStorage(report_root)
    for config in configurations:
        research = evaluate_candidate_research(integrity, calendar, config)
        first = build_candidate_research_run(
            integrity, calendar, research,
            created_at=created_at, implementation_revision=implementation_revision,
        )
        second = build_candidate_research_run(
            integrity, calendar, research,
            created_at=created_at, implementation_revision=implementation_revision,
        )
        first_id = report_identifier(first.content)
        second_id = report_identifier(second.content)
        stored = storage.save(first)
        verification = verify_report(stored.report_path)
        reproducible = first_id == second_id == stored.report_id and verification.valid
        evidence.append(PipelineEvidence(
            research.strategy_name, research.strategy_version,
            research.configuration_fingerprint, stored.report_id,
            len(research.setups), second_id, reproducible,
        ))
    return tuple(evidence)


__all__ = [
    "ReportStorageError",
    "resolve_implementation_revision",
    "verify_candidate_pipeline",
]
