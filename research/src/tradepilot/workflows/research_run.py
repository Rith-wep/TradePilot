"""Shared orchestration for deterministic candidate research runs."""

from dataclasses import dataclass
from datetime import datetime

from tradepilot.data.integrity import IntegrityReport
from tradepilot.data.sessions import TradingSessionCalendar
from tradepilot.indicators import atr, ema, rsi
from tradepilot.reporting.models import IndicatorParameter, ResearchRun
from tradepilot.reporting.validation import build_research_run
from tradepilot.strategies.base import configuration_fingerprint
from tradepilot.strategies.breakout import BreakoutConfig, PriceRangeBreakoutStrategy
from tradepilot.strategies.models import SetupRecord, StrategyIndicators
from tradepilot.strategies.pullback import EmaRsiPullbackStrategy, PullbackConfig


StrategyConfig = BreakoutConfig | PullbackConfig


@dataclass(frozen=True, slots=True)
class CandidateResearch:
    config: StrategyConfig
    strategy_name: str
    strategy_version: str
    configuration_fingerprint: str
    indicator_parameters: tuple[IndicatorParameter, ...]
    setups: tuple[SetupRecord, ...]


def evaluate_candidate_research(
    integrity: IntegrityReport,
    calendar: TradingSessionCalendar,
    config: StrategyConfig,
) -> CandidateResearch:
    """Calculate required indicators and detect candidates for one config."""
    values = integrity.candles
    if isinstance(config, BreakoutConfig):
        strategy = PriceRangeBreakoutStrategy(config)
        atr_series = (
            atr(values, config.atr_period, config.price_basis)
            if config.minimum_breakout_atr is not None else None
        )
        indicators = StrategyIndicators(atr=atr_series)
        parameters = (
            (IndicatorParameter("ATR", config.atr_period, config.price_basis),)
            if config.minimum_breakout_atr is not None else ()
        )
    elif isinstance(config, PullbackConfig):
        strategy = EmaRsiPullbackStrategy(config)
        indicators = StrategyIndicators(
            ema=ema(values, config.ema_period, config.price_basis),
            rsi=rsi(values, config.rsi_period, config.price_basis),
            atr=atr(values, config.atr_period, config.price_basis),
        )
        parameters = (
            IndicatorParameter("EMA", config.ema_period, config.price_basis),
            IndicatorParameter("RSI", config.rsi_period, config.price_basis),
            IndicatorParameter("ATR", config.atr_period, config.price_basis),
        )
    else:
        raise TypeError(f"unsupported strategy configuration: {type(config).__name__}")

    fingerprint = configuration_fingerprint(
        strategy.name, strategy.version, config, calendar.calendar_id,
    )
    setups = strategy.detect(values, indicators, calendar)
    return CandidateResearch(
        config, strategy.name, strategy.version, fingerprint, parameters, setups,
    )


def build_candidate_research_run(
    integrity: IntegrityReport,
    calendar: TradingSessionCalendar,
    research: CandidateResearch,
    *,
    created_at: datetime,
    implementation_revision: str,
) -> ResearchRun:
    """Build an immutable candidate report from an evaluated configuration."""
    return build_research_run(
        integrity,
        strategy_name=research.strategy_name,
        strategy_version=research.strategy_version,
        configuration_fingerprint=research.configuration_fingerprint,
        strategy_configuration=research.config,
        indicator_parameters=research.indicator_parameters,
        session_calendar_id=calendar.calendar_id,
        reject_unexpected_gaps=research.config.reject_unexpected_gaps,
        setups=research.setups,
        created_at=created_at,
        implementation_revision=implementation_revision,
    )


__all__ = [
    "CandidateResearch",
    "StrategyConfig",
    "build_candidate_research_run",
    "evaluate_candidate_research",
]
