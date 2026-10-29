"""Research verification workflow for integrity-verified real-data snapshots."""

from datetime import datetime
from pathlib import Path

from tradepilot.data.integrity import IntegrityReport
from tradepilot.data.readiness import PipelineEvidence
from tradepilot.data.sessions import TradingSessionCalendar
from tradepilot.indicators import atr, ema, rsi
from tradepilot.reporting.models import IndicatorParameter
from tradepilot.reporting.storage import ReportStorage, ReportStorageError, report_identifier, verify_report
from tradepilot.reporting.validation import build_research_run, resolve_implementation_revision
from tradepilot.strategies.base import configuration_fingerprint
from tradepilot.strategies.breakout import BreakoutConfig, PriceRangeBreakoutStrategy
from tradepilot.strategies.models import StrategyIndicators
from tradepilot.strategies.pullback import EmaRsiPullbackStrategy, PullbackConfig


def verify_candidate_pipeline(
    integrity: IntegrityReport,
    calendar: TradingSessionCalendar,
    report_root: str | Path,
    *,
    implementation_revision: str,
    created_at: datetime,
) -> tuple[PipelineEvidence, ...]:
    """Run unchanged default strategies; zero candidates are a valid outcome."""
    values = integrity.candles
    configurations = (
        (PriceRangeBreakoutStrategy(BreakoutConfig()), BreakoutConfig(), StrategyIndicators(), ()),
        (
            EmaRsiPullbackStrategy(PullbackConfig()), PullbackConfig(),
            StrategyIndicators(
                ema=ema(values, 200, "mid"),
                rsi=rsi(values, 14, "mid"),
                atr=atr(values, 14, "mid"),
            ),
            (
                IndicatorParameter("EMA", 200, "mid"),
                IndicatorParameter("RSI", 14, "mid"),
                IndicatorParameter("ATR", 14, "mid"),
            ),
        ),
    )
    evidence = []
    storage = ReportStorage(report_root)
    for strategy, config, indicators, parameters in configurations:
        fingerprint = configuration_fingerprint(strategy.name, strategy.version, config, calendar.calendar_id)
        setups = strategy.detect(values, indicators, calendar)
        first = build_research_run(
            integrity, strategy_name=strategy.name, strategy_version=strategy.version,
            configuration_fingerprint=fingerprint, strategy_configuration=config,
            indicator_parameters=parameters, session_calendar_id=calendar.calendar_id,
            reject_unexpected_gaps=config.reject_unexpected_gaps, setups=setups,
            created_at=created_at, implementation_revision=implementation_revision,
        )
        second = build_research_run(
            integrity, strategy_name=strategy.name, strategy_version=strategy.version,
            configuration_fingerprint=fingerprint, strategy_configuration=config,
            indicator_parameters=parameters, session_calendar_id=calendar.calendar_id,
            reject_unexpected_gaps=config.reject_unexpected_gaps, setups=setups,
            created_at=created_at, implementation_revision=implementation_revision,
        )
        first_id = report_identifier(first.content)
        second_id = report_identifier(second.content)
        stored = storage.save(first)
        verification = verify_report(stored.report_path)
        reproducible = first_id == second_id == stored.report_id and verification.valid
        evidence.append(PipelineEvidence(
            strategy.name, strategy.version, fingerprint, stored.report_id,
            len(setups), second_id, reproducible,
        ))
    return tuple(evidence)


__all__ = [
    "ReportStorageError",
    "resolve_implementation_revision",
    "verify_candidate_pipeline",
]
