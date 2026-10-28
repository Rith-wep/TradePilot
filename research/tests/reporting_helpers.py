import tempfile
from datetime import datetime, timedelta, timezone

from ingestion_helpers import EURUSD
from strategy_helpers import strategy_candle
from tradepilot.data.integrity import verify_dataset
from tradepilot.data.sessions import WeeklySessionCalendar
from tradepilot.data.storage import ParquetDatasetStore
from tradepilot.reporting.models import IndicatorParameter
from tradepilot.reporting.validation import build_research_run
from tradepilot.strategies.base import configuration_fingerprint
from tradepilot.strategies.breakout import BreakoutConfig, PriceRangeBreakoutStrategy
from tradepilot.strategies.models import StrategyIndicators


CREATED_AT = datetime(2024, 3, 1, tzinfo=timezone.utc)


def create_context(directory: str, *, extra_candle: bool = False):
    store = ParquetDatasetStore(directory)
    candles = [
        strategy_candle(0, "9", high="10", low="8"),
        strategy_candle(1, "10", high="11", low="9"),
        strategy_candle(2, "12", high="12.5", low="10"),
    ]
    if extra_candle:
        candles.append(strategy_candle(3, "11", high="12", low="10"))
    store.save(
        "mock", EURUSD, "H1", candles,
        retrieved_at=datetime(2024, 2, 1, tzinfo=timezone.utc),
        request_start=candles[0].timestamp,
        request_end=candles[-1].timestamp + timedelta(hours=1),
    )
    root = store.dataset_directory("mock", EURUSD, "H1")
    integrity = verify_dataset(root)
    calendar = WeeklySessionCalendar(name="research-calendar")
    config = BreakoutConfig(lookback=2)
    strategy = PriceRangeBreakoutStrategy(config)
    fingerprint = configuration_fingerprint(strategy.name, strategy.version, config, calendar.calendar_id)
    setups = strategy.detect(integrity.candles, StrategyIndicators(), calendar)
    return root, integrity, calendar, config, strategy, fingerprint, setups


def build_run(integrity, calendar, config, strategy, fingerprint, setups, *, created_at=CREATED_AT, revision="abc123"):
    return build_research_run(
        integrity,
        strategy_name=strategy.name,
        strategy_version=strategy.version,
        configuration_fingerprint=fingerprint,
        strategy_configuration=config,
        indicator_parameters=(),
        session_calendar_id=calendar.calendar_id,
        reject_unexpected_gaps=config.reject_unexpected_gaps,
        setups=setups,
        created_at=created_at,
        implementation_revision=revision,
    )

