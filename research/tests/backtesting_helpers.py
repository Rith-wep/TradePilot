from datetime import datetime, timedelta, timezone
from decimal import Decimal

from tradepilot.backtesting.config import BACKTEST_CONFIG_SCHEMA_VERSION, EXECUTION_MODEL_VERSION, BacktestConfig
from tradepilot.backtesting.events import OpeningQuoteEvent
from tradepilot.backtesting.models import BacktestProvenance, InstrumentSpec, TradeDirection
from tradepilot.backtesting.orders import OrderRequest
from tradepilot.backtesting.policies import (
    AmbiguityPolicy,
    CommissionModel,
    ExecutionPolicy,
    FinancingModel,
    FinancingPolicy,
    GapStopPolicy,
    OpeningTargetPolicy,
    OrderType,
    RiskPolicy,
    TransactionCostPolicy,
    UnexpectedGapPolicy,
)


UTC = timezone.utc
OPEN = datetime(2024, 1, 2, 10, tzinfo=UTC)
OBSERVABLE = OPEN + timedelta(hours=1)
HASH_A = "a" * 64
HASH_B = "b" * 64
HASH_C = "c" * 64
HASH_D = "d" * 64


def provenance() -> BacktestProvenance:
    return BacktestProvenance(HASH_A, HASH_B, HASH_C, "strategy", "1.0.0", HASH_D, "revision")


def instrument(quote_currency: str = "USD") -> InstrumentSpec:
    return InstrumentSpec("EUR" + quote_currency, "EUR", quote_currency, Decimal("0.0001"), 5, Decimal("1000"))


def config(account_currency: str = "USD", quote_currency: str = "USD", provenance_value=None) -> BacktestConfig:
    return BacktestConfig(
        BACKTEST_CONFIG_SCHEMA_VERSION,
        EXECUTION_MODEL_VERSION,
        provenance_value or provenance(),
        instrument(quote_currency),
        "H1",
        account_currency,
        "calendar-v1",
        ExecutionPolicy(
            "1", OrderType.MARKET_NEXT_ELIGIBLE_OPEN, UnexpectedGapPolicy.REJECT,
            AmbiguityPolicy.CONSERVATIVE_STOP_FIRST, GapStopPolicy.EXECUTABLE_OPEN,
            OpeningTargetPolicy.EXECUTABLE_OPEN, Decimal("0"), Decimal("0"),
        ),
        TransactionCostPolicy("1", CommissionModel.NONE, Decimal("0")),
        FinancingPolicy("1", FinancingModel.NONE),
        RiskPolicy("1", 1, Decimal("100000")),
    )


def order(direction: TradeDirection = TradeDirection.LONG, **changes) -> OrderRequest:
    values = dict(
        order_id="order-1", candidate_key="candidate-1",
        order_type=OrderType.MARKET_NEXT_ELIGIBLE_OPEN, direction=direction,
        instrument="EURUSD", quantity=Decimal("10000"),
        detection_candle_open_time=OPEN, signal_observable_at=OBSERVABLE,
        created_at=OBSERVABLE, earliest_execution_at=OBSERVABLE,
        expires_at=OBSERVABLE + timedelta(hours=2), stop_loss=None, take_profit=None,
        provenance=provenance(),
    )
    values.update(changes)
    return OrderRequest(**values)


def opening_quote(at=OBSERVABLE) -> OpeningQuoteEvent:
    return OpeningQuoteEvent("EURUSD", "H1", at, at, Decimal("1.1000"), Decimal("1.1002"), HASH_A, HASH_B)
