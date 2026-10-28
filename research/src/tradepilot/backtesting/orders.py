"""Market-at-next-open requests and immutable order lifecycle facts."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum

from tradepilot.backtesting.models import BacktestProvenance, TradeDirection, require_positive_decimal, require_utc
from tradepilot.backtesting.policies import OrderType


class OrderState(str, Enum):
    CREATED = "CREATED"
    PENDING = "PENDING"
    FILLED = "FILLED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


VALID_TRANSITIONS: dict[OrderState, frozenset[OrderState]] = {
    OrderState.CREATED: frozenset({OrderState.PENDING, OrderState.REJECTED, OrderState.CANCELLED}),
    OrderState.PENDING: frozenset({OrderState.FILLED, OrderState.REJECTED, OrderState.CANCELLED, OrderState.EXPIRED}),
    OrderState.FILLED: frozenset(),
    OrderState.REJECTED: frozenset(),
    OrderState.CANCELLED: frozenset(),
    OrderState.EXPIRED: frozenset(),
}


@dataclass(frozen=True, slots=True)
class OrderRequest:
    order_id: str
    candidate_key: str
    order_type: OrderType
    direction: TradeDirection
    instrument: str
    quantity: Decimal
    detection_candle_open_time: datetime
    signal_observable_at: datetime
    created_at: datetime
    earliest_execution_at: datetime
    expires_at: datetime
    stop_loss: Decimal | None
    take_profit: Decimal | None
    provenance: BacktestProvenance

    def __post_init__(self) -> None:
        if not self.order_id.strip() or not self.candidate_key.strip():
            raise ValueError("order_id and candidate_key must not be empty")
        if self.order_type is not OrderType.MARKET_NEXT_ELIGIBLE_OPEN:
            raise ValueError("only market-at-next-eligible-open requests are supported")
        require_positive_decimal("quantity", self.quantity)
        for name in (
            "detection_candle_open_time", "signal_observable_at", "created_at",
            "earliest_execution_at", "expires_at",
        ):
            require_utc(name, getattr(self, name))
        if self.signal_observable_at <= self.detection_candle_open_time:
            raise ValueError("signal must become observable after detection candle open")
        if self.created_at < self.signal_observable_at:
            raise ValueError("order cannot be created before signal observability")
        if self.earliest_execution_at < self.signal_observable_at:
            raise ValueError("execution cannot precede signal observability")
        if self.expires_at <= self.earliest_execution_at:
            raise ValueError("order expiry must be after earliest execution time")
        for name in ("stop_loss", "take_profit"):
            value = getattr(self, name)
            if value is not None:
                require_positive_decimal(name, value)


@dataclass(frozen=True, slots=True)
class OrderLifecycleEvent:
    event_id: str
    order_id: str
    previous_state: OrderState | None
    state: OrderState
    occurred_at: datetime
    reason: str

    def __post_init__(self) -> None:
        if not self.event_id.strip() or not self.order_id.strip() or not self.reason.strip():
            raise ValueError("event identity and reason must not be empty")
        require_utc("occurred_at", self.occurred_at)
        if self.previous_state is None:
            if self.state is not OrderState.CREATED:
                raise ValueError("the first lifecycle event must create the order")
        elif self.state not in VALID_TRANSITIONS[self.previous_state]:
            raise ValueError(f"invalid order transition: {self.previous_state.value} -> {self.state.value}")


def validate_transition(previous: OrderState, next_state: OrderState) -> None:
    if next_state not in VALID_TRANSITIONS[previous]:
        raise ValueError(f"invalid order transition: {previous.value} -> {next_state.value}")
