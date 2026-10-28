"""Immutable position states created only from validated entry fills."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum

from tradepilot.backtesting.models import TradeDirection, require_currency, require_positive_decimal, require_utc
from tradepilot.backtesting.events import FillEvent, FillPurpose
from tradepilot.backtesting.orders import OrderRequest, OrderState


class PositionStatus(str, Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"


@dataclass(frozen=True, slots=True)
class PositionState:
    position_id: str
    order_id: str
    entry_fill_id: str
    instrument: str
    direction: TradeDirection
    quantity: Decimal
    entry_price: Decimal
    entry_at: datetime
    account_currency: str
    quote_currency: str
    stop_loss: Decimal | None
    take_profit: Decimal | None
    status: PositionStatus = PositionStatus.OPEN
    exit_fill_id: str | None = None
    exit_price: Decimal | None = None
    exit_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.position_id.strip() or not self.order_id.strip() or not self.entry_fill_id.strip():
            raise ValueError("position and originating identities must not be empty")
        require_positive_decimal("quantity", self.quantity)
        require_positive_decimal("entry_price", self.entry_price)
        require_utc("entry_at", self.entry_at)
        require_currency("account_currency", self.account_currency)
        require_currency("quote_currency", self.quote_currency)
        if self.status is PositionStatus.OPEN:
            if any(value is not None for value in (self.exit_fill_id, self.exit_price, self.exit_at)):
                raise ValueError("open position must not contain exit details")
        else:
            if self.exit_fill_id is None or self.exit_price is None or self.exit_at is None:
                raise ValueError("closed position requires complete exit details")
            require_positive_decimal("exit_price", self.exit_price)
            require_utc("exit_at", self.exit_at)
            if self.exit_at < self.entry_at:
                raise ValueError("position exit cannot precede entry")


def position_from_entry_fill(
    position_id: str,
    order: OrderRequest,
    order_state: OrderState,
    fill: FillEvent,
    *,
    account_currency: str,
    quote_currency: str,
) -> PositionState:
    """Create an open position only from a valid pending-order entry fill."""

    from tradepilot.backtesting.validation import validate_fill

    validate_fill(order, order_state, fill)
    if fill.purpose is not FillPurpose.ENTRY:
        raise ValueError("position requires an entry fill")
    if order.direction is TradeDirection.LONG:
        if order.stop_loss is not None and order.stop_loss >= fill.execution_price:
            raise ValueError("LONG stop_loss must be below entry price")
        if order.take_profit is not None and order.take_profit <= fill.execution_price:
            raise ValueError("LONG take_profit must be above entry price")
    else:
        if order.stop_loss is not None and order.stop_loss <= fill.execution_price:
            raise ValueError("SHORT stop_loss must be above entry price")
        if order.take_profit is not None and order.take_profit >= fill.execution_price:
            raise ValueError("SHORT take_profit must be below entry price")
    return PositionState(
        position_id, order.order_id, fill.fill_id, order.instrument, order.direction,
        fill.quantity, fill.execution_price, fill.filled_at, account_currency,
        quote_currency, order.stop_loss, order.take_profit,
    )
