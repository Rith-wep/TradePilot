import tempfile
import unittest

from readiness_helpers import real_candles, stored_integrity
from reporting_helpers import CREATED_AT, build_run, create_context
from simulator_helpers import START
from tradepilot.data.sessions import WeeklySessionCalendar
from tradepilot.indicators import atr, ema, rsi
from tradepilot.reporting.models import IndicatorParameter
from tradepilot.reporting.storage import report_identifier
from tradepilot.reporting.validation import build_research_run
from tradepilot.strategies.base import configuration_fingerprint
from tradepilot.strategies.models import StrategyIndicators
from tradepilot.strategies.pullback import EmaRsiPullbackStrategy, PullbackConfig
from tradepilot.workflows.research_run import (
    build_candidate_research_run,
    evaluate_candidate_research,
)


class ResearchRunWorkflowTests(unittest.TestCase):
    def test_breakout_matches_previous_construction_and_exact_report_id(self):
        with tempfile.TemporaryDirectory() as root:
            _, integrity, calendar, config, strategy, fingerprint, setups = create_context(root)
            previous = build_run(
                integrity, calendar, config, strategy, fingerprint, setups,
            )
            evaluated = evaluate_candidate_research(integrity, calendar, config)
            current = build_candidate_research_run(
                integrity,
                calendar,
                evaluated,
                created_at=CREATED_AT,
                implementation_revision="abc123",
            )

        self.assertEqual(evaluated.setups, setups)
        self.assertEqual(evaluated.configuration_fingerprint, fingerprint)
        self.assertEqual(current.content, previous.content)
        self.assertEqual(
            report_identifier(current.content),
            "77fd547c8dd00072b9479140ae689586d5f921c0ecf45afb91e2940962b436ad",
        )

    def test_pullback_matches_previous_indicator_and_report_construction(self):
        with tempfile.TemporaryDirectory() as root:
            integrity, _ = stored_integrity(root, real_candles())
            calendar = WeeklySessionCalendar(name="workflow-test")
            config = PullbackConfig()
            strategy = EmaRsiPullbackStrategy(config)
            indicators = StrategyIndicators(
                ema=ema(integrity.candles, 200, "mid"),
                rsi=rsi(integrity.candles, 14, "mid"),
                atr=atr(integrity.candles, 14, "mid"),
            )
            fingerprint = configuration_fingerprint(
                strategy.name, strategy.version, config, calendar.calendar_id,
            )
            setups = strategy.detect(integrity.candles, indicators, calendar)
            parameters = (
                IndicatorParameter("EMA", 200, "mid"),
                IndicatorParameter("RSI", 14, "mid"),
                IndicatorParameter("ATR", 14, "mid"),
            )
            previous = build_research_run(
                integrity,
                strategy_name=strategy.name,
                strategy_version=strategy.version,
                configuration_fingerprint=fingerprint,
                strategy_configuration=config,
                indicator_parameters=parameters,
                session_calendar_id=calendar.calendar_id,
                reject_unexpected_gaps=config.reject_unexpected_gaps,
                setups=setups,
                created_at=START,
                implementation_revision="test-revision",
            )
            evaluated = evaluate_candidate_research(integrity, calendar, config)
            current = build_candidate_research_run(
                integrity,
                calendar,
                evaluated,
                created_at=START,
                implementation_revision="test-revision",
            )

        self.assertEqual(evaluated.setups, setups)
        self.assertEqual(evaluated.indicator_parameters, parameters)
        self.assertEqual(current.content, previous.content)
        self.assertEqual(
            report_identifier(current.content),
            "d7c148b59dea0b50e89be17f55664c8eac9a672211232be6ce14dfcc700a4eaf",
        )


if __name__ == "__main__":
    unittest.main()
