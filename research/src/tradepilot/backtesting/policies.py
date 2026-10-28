"""Explicit execution, cost, financing, risk, and uncertainty policies."""

from dataclasses import dataclass
from datetime import time
from decimal import Decimal
from enum import Enum

from tradepilot.backtesting.models import require_nonnegative_decimal, require_positive_decimal


class OrderType(str, Enum):
    MARKET_NEXT_ELIGIBLE_OPEN = "MARKET_NEXT_ELIGIBLE_OPEN"


class UnexpectedGapPolicy(str, Enum):
    REJECT = "REJECT"


class AmbiguityPolicy(str, Enum):
    CONSERVATIVE_STOP_FIRST = "CONSERVATIVE_STOP_FIRST"
    LOWER_TIMEFRAME_RECONSTRUCTION = "LOWER_TIMEFRAME_RECONSTRUCTION"


class OpeningTargetPolicy(str, Enum):
    EXECUTABLE_OPEN = "EXECUTABLE_OPEN"


class GapStopPolicy(str, Enum):
    EXECUTABLE_OPEN = "EXECUTABLE_OPEN"


class CommissionModel(str, Enum):
    NONE = "NONE"
    FIXED = "FIXED"
    PER_UNIT = "PER_UNIT"


class FinancingModel(str, Enum):
    NONE = "NONE"
    EXPLICIT_RATES = "EXPLICIT_RATES"


@dataclass(frozen=True, slots=True)
class ExecutionPolicy:
    version: str
    order_type: OrderType
    unexpected_gap_policy: UnexpectedGapPolicy
    ambiguity_policy: AmbiguityPolicy
    gap_stop_policy: GapStopPolicy
    opening_target_policy: OpeningTargetPolicy
    additional_spread_pips: Decimal
    slippage_pips: Decimal

    def __post_init__(self) -> None:
        if not self.version.strip():
            raise ValueError("execution policy version must not be empty")
        if self.order_type is not OrderType.MARKET_NEXT_ELIGIBLE_OPEN:
            raise ValueError("only market-at-next-eligible-open orders are supported")
        if self.unexpected_gap_policy is not UnexpectedGapPolicy.REJECT:
            raise ValueError("the MVP requires strict unexpected-gap rejection")
        require_nonnegative_decimal("additional_spread_pips", self.additional_spread_pips)
        require_nonnegative_decimal("slippage_pips", self.slippage_pips)


@dataclass(frozen=True, slots=True)
class TransactionCostPolicy:
    version: str
    commission_model: CommissionModel
    commission_amount: Decimal

    def __post_init__(self) -> None:
        if not self.version.strip():
            raise ValueError("cost policy version must not be empty")
        require_nonnegative_decimal("commission_amount", self.commission_amount)
        if self.commission_model is CommissionModel.NONE and self.commission_amount != 0:
            raise ValueError("NONE commission must have a zero amount")


@dataclass(frozen=True, slots=True)
class FinancingPolicy:
    version: str
    model: FinancingModel
    rollover_time: time | None = None
    timezone_name: str | None = None
    long_rate: Decimal | None = None
    short_rate: Decimal | None = None

    def __post_init__(self) -> None:
        if not self.version.strip():
            raise ValueError("financing policy version must not be empty")
        supplied = (self.rollover_time, self.timezone_name, self.long_rate, self.short_rate)
        if self.model is FinancingModel.NONE:
            if any(value is not None for value in supplied):
                raise ValueError("NONE financing must not contain rollover assumptions")
            return
        if any(value is None for value in supplied):
            raise ValueError("explicit financing requires time, timezone, and long/short rates")
        if not self.timezone_name or not self.timezone_name.strip():
            raise ValueError("financing timezone must not be empty")
        for name, value in (("long_rate", self.long_rate), ("short_rate", self.short_rate)):
            if not isinstance(value, Decimal) or not value.is_finite():
                raise ValueError(f"{name} must be a finite Decimal")


@dataclass(frozen=True, slots=True)
class RiskPolicy:
    version: str
    max_open_positions: int
    max_quantity: Decimal

    def __post_init__(self) -> None:
        if not self.version.strip():
            raise ValueError("risk policy version must not be empty")
        if self.max_open_positions != 1:
            raise ValueError("the MVP requires one position at a time")
        require_positive_decimal("max_quantity", self.max_quantity)
