"""Immutable market and fill events with explicit information availability."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum, IntEnum

from tradepilot.backtesting.models import (
    BacktestProvenance,
    InstrumentSpec,
    TradeDirection,
    require_positive_decimal,
    require_sha256,
    require_utc,
)


class BoundaryEventPriority(IntEnum):
    CANDLE_COMPLETED = 10
    SIGNAL_OBSERVABLE = 20
    OPENING_QUOTE = 30


class FillPurpose(str, Enum):
    ENTRY = "ENTRY"
    EXIT = "EXIT"


class PriceSide(str, Enum):
    BID = "BID"
    ASK = "ASK"


@dataclass(frozen=True, slots=True)
class OpeningQuoteEvent:
    instrument: str
    timeframe: str
    candle_open_time: datetime
    available_at: datetime
    bid_open: Decimal
    ask_open: Decimal
    dataset_id: str
    dataset_checksum: str

    def __post_init__(self) -> None:
        require_utc("candle_open_time", self.candle_open_time)
        require_utc("available_at", self.available_at)
        if self.available_at != self.candle_open_time:
            raise ValueError("opening quote must become available at candle open")
        require_positive_decimal("bid_open", self.bid_open)
        require_positive_decimal("ask_open", self.ask_open)
        if self.bid_open > self.ask_open:
            raise ValueError("opening bid must not exceed opening ask")
        require_sha256("dataset_id", self.dataset_id)
        require_sha256("dataset_checksum", self.dataset_checksum)


@dataclass(frozen=True, slots=True)
class CompletedCandleEvent:
    instrument: str
    timeframe: str
    candle_open_time: datetime
    available_at: datetime
    bid_open: Decimal
    bid_high: Decimal
    bid_low: Decimal
    bid_close: Decimal
    ask_open: Decimal
    ask_high: Decimal
    ask_low: Decimal
    ask_close: Decimal
    dataset_id: str
    dataset_checksum: str

    def __post_init__(self) -> None:
        require_utc("candle_open_time", self.candle_open_time)
        require_utc("available_at", self.available_at)
        if self.timeframe != "H1":
            raise ValueError("only H1 completed-candle timing is supported")
        if self.available_at != self.candle_open_time + timedelta(hours=1):
            raise ValueError("completed H1 candle is available only at candle close")
        for side in ("bid", "ask"):
            open_ = getattr(self, f"{side}_open")
            high = getattr(self, f"{side}_high")
            low = getattr(self, f"{side}_low")
            close = getattr(self, f"{side}_close")
            for field, value in (("open", open_), ("high", high), ("low", low), ("close", close)):
                require_positive_decimal(f"{side}_{field}", value)
            if low > high or not low <= open_ <= high or not low <= close <= high:
                raise ValueError(f"invalid {side} OHLC")
        if any(bid > ask for bid, ask in zip(
            (self.bid_open, self.bid_high, self.bid_low, self.bid_close),
            (self.ask_open, self.ask_high, self.ask_low, self.ask_close),
        )):
            raise ValueError("bid prices must not exceed corresponding ask prices")
        require_sha256("dataset_id", self.dataset_id)
        require_sha256("dataset_checksum", self.dataset_checksum)


@dataclass(frozen=True, slots=True)
class FillEvent:
    fill_id: str
    order_id: str
    purpose: FillPurpose
    direction: TradeDirection
    filled_at: datetime
    quantity: Decimal
    price_side: PriceSide
    quoted_price: Decimal
    spread_stress: Decimal
    slippage: Decimal
    execution_price: Decimal
    commission: Decimal
    provenance: BacktestProvenance

    def __post_init__(self) -> None:
        if not self.fill_id.strip() or not self.order_id.strip():
            raise ValueError("fill_id and order_id must not be empty")
        require_utc("filled_at", self.filled_at)
        require_positive_decimal("quantity", self.quantity)
        require_positive_decimal("quoted_price", self.quoted_price)
        require_positive_decimal("execution_price", self.execution_price)
        for name in ("spread_stress", "slippage", "commission"):
            value = getattr(self, name)
            if not isinstance(value, Decimal) or not value.is_finite() or value < 0:
                raise ValueError(f"{name} must be a non-negative finite Decimal")


def event_sort_key(available_at: datetime, priority: BoundaryEventPriority) -> tuple[datetime, int]:
    require_utc("available_at", available_at)
    return available_at, int(priority)


def required_price_side(direction: TradeDirection, purpose: FillPurpose) -> PriceSide:
    if purpose is FillPurpose.ENTRY:
        return PriceSide.ASK if direction is TradeDirection.LONG else PriceSide.BID
    return PriceSide.BID if direction is TradeDirection.LONG else PriceSide.ASK


def stressed_opening_price(
    quote: OpeningQuoteEvent,
    instrument: InstrumentSpec,
    direction: TradeDirection,
    purpose: FillPurpose,
    *,
    additional_spread_pips: Decimal,
    slippage_pips: Decimal,
) -> tuple[PriceSide, Decimal]:
    """Return the adverse executable price using opening information only."""

    if quote.instrument != instrument.symbol:
        raise ValueError("quote instrument does not match instrument specification")
    for name, value in (("additional_spread_pips", additional_spread_pips), ("slippage_pips", slippage_pips)):
        if not isinstance(value, Decimal) or not value.is_finite() or value < 0:
            raise ValueError(f"{name} must be a non-negative finite Decimal")
    side = required_price_side(direction, purpose)
    raw = quote.ask_open if side is PriceSide.ASK else quote.bid_open
    half_stress = additional_spread_pips * instrument.pip_size / Decimal(2)
    slippage = slippage_pips * instrument.pip_size
    buy = side is PriceSide.ASK
    execution_price = raw + half_stress + slippage if buy else raw - half_stress - slippage
    require_positive_decimal("stressed execution price", execution_price)
    return side, execution_price
