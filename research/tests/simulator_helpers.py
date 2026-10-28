from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

from backtesting_helpers import HASH_A, HASH_B, HASH_C, HASH_D
from tradepilot.backtesting.config import BACKTEST_CONFIG_SCHEMA_VERSION, EXECUTION_MODEL_VERSION, BacktestConfig
from tradepilot.backtesting.models import BacktestProvenance, InstrumentSpec
from tradepilot.backtesting.policies import (
    AmbiguityPolicy, CommissionModel, ExecutionPolicy, FinancingModel,
    FinancingPolicy, GapStopPolicy, OpeningTargetPolicy, OrderType,
    RiskPolicy, TransactionCostPolicy, UnexpectedGapPolicy,
)
from tradepilot.backtesting.signal_policy import SignalOrderPolicy
from tradepilot.backtesting.simulation_models import SimulationCandidateReport, SimulationConfig
from tradepilot.data.models import Candle, Instrument
from tradepilot.data.sessions import WeeklySessionCalendar
from tradepilot.strategies.models import Direction, SetupRecord


UTC = timezone.utc
START = datetime(2024, 1, 2, 10, tzinfo=UTC)
DATA_INSTRUMENT = Instrument("EURUSD", "EUR", "USD", Decimal("0.0001"), 5)
REPORT_ID = HASH_C


def candle(hour: int, *, bid_open="1.10000", bid_high="1.10100", bid_low="1.09900", bid_close="1.10050") -> Candle:
    spread = Decimal("0.00020")
    return Candle(
        DATA_INSTRUMENT, START + timedelta(hours=hour), "H1",
        Decimal(bid_open), Decimal(bid_high), Decimal(bid_low), Decimal(bid_close),
        Decimal(bid_open) + spread, Decimal(bid_high) + spread,
        Decimal(bid_low) + spread, Decimal(bid_close) + spread,
        "synthetic", "v1", True,
    )


def setup(detection_hour: int = 0, direction: Direction = Direction.LONG) -> SetupRecord:
    detection = START + timedelta(hours=detection_hour)
    return SetupRecord(
        "strategy", "1.0.0", "EURUSD", "H1", detection,
        detection + timedelta(hours=1), direction, "synthetic", (), (), (),
        Decimal("1.09000"), HASH_D,
    )


def build_context(
    candles=None,
    signals=None,
    *,
    expiry_hours=2,
    holding=2,
    stop_pips=None,
    target_pips=None,
    spread_pips="0",
    slippage_pips="0",
    financing=FinancingModel.NONE,
    calendar=None,
):
    candles = tuple(candles or (candle(0), candle(1), candle(2)))
    signals = tuple(signals or (setup(),))
    calendar = calendar or WeeklySessionCalendar(name="simulation-calendar")
    provenance = BacktestProvenance(HASH_A, HASH_B, REPORT_ID, "strategy", "1.0.0", HASH_D, "revision")
    instrument = InstrumentSpec("EURUSD", "EUR", "USD", Decimal("0.0001"), 5, Decimal("1000"))
    financing_policy = (
        FinancingPolicy("1", FinancingModel.NONE)
        if financing is FinancingModel.NONE else
        FinancingPolicy(
            "1", FinancingModel.EXPLICIT_RATES,
            datetime.min.time(), "UTC", Decimal("0"), Decimal("0"),
        )
    )
    base = BacktestConfig(
        BACKTEST_CONFIG_SCHEMA_VERSION, EXECUTION_MODEL_VERSION, provenance,
        instrument, "H1", "USD", calendar.calendar_id,
        ExecutionPolicy(
            "1", OrderType.MARKET_NEXT_ELIGIBLE_OPEN, UnexpectedGapPolicy.REJECT,
            AmbiguityPolicy.CONSERVATIVE_STOP_FIRST, GapStopPolicy.EXECUTABLE_OPEN,
            OpeningTargetPolicy.EXECUTABLE_OPEN, Decimal(spread_pips), Decimal(slippage_pips),
        ),
        TransactionCostPolicy("1", CommissionModel.NONE, Decimal("0")),
        financing_policy, RiskPolicy("1", 1, Decimal("100000")),
    )
    policy = SignalOrderPolicy(
        "1", Decimal("10000"), timedelta(hours=expiry_hours), holding,
        Decimal(stop_pips) if stop_pips is not None else None,
        Decimal(target_pips) if target_pips is not None else None,
    )
    report = SimulationCandidateReport(
        REPORT_ID, HASH_A, HASH_B, "EURUSD", "H1", "strategy", "1.0.0",
        HASH_D, calendar.calendar_id, signals,
    )
    integrity = SimpleNamespace(
        valid=True, candles=candles, dataset_id=HASH_A, dataset_checksum=HASH_B,
    )
    return integrity, report, SimulationConfig(base, policy), calendar
