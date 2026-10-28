"""Explicit versioned conversion policy from research candidates to orders."""

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from enum import Enum

from tradepilot.backtesting.models import require_nonnegative_decimal, require_positive_decimal


class EndOfDatasetPolicy(str, Enum):
    CLOSE_AT_FINAL_COMPLETED_CANDLE = "CLOSE_AT_FINAL_COMPLETED_CANDLE"


class CompetingSignalPolicy(str, Enum):
    REJECT_OPPOSING_SELECT_CANONICAL = "REJECT_OPPOSING_SELECT_CANONICAL"


@dataclass(frozen=True, slots=True)
class SignalOrderPolicy:
    version: str
    quantity: Decimal
    entry_expiry: timedelta
    max_holding_candles: int
    stop_distance_pips: Decimal | None
    target_distance_pips: Decimal | None
    end_of_dataset_policy: EndOfDatasetPolicy = EndOfDatasetPolicy.CLOSE_AT_FINAL_COMPLETED_CANDLE
    competing_signal_policy: CompetingSignalPolicy = CompetingSignalPolicy.REJECT_OPPOSING_SELECT_CANONICAL

    def __post_init__(self) -> None:
        if not self.version.strip():
            raise ValueError("signal-order policy version must not be empty")
        require_positive_decimal("quantity", self.quantity)
        if self.entry_expiry <= timedelta(0):
            raise ValueError("entry_expiry must be positive")
        if isinstance(self.max_holding_candles, bool) or not isinstance(self.max_holding_candles, int) or self.max_holding_candles <= 0:
            raise ValueError("max_holding_candles must be a positive integer")
        for name in ("stop_distance_pips", "target_distance_pips"):
            value = getattr(self, name)
            if value is not None:
                require_positive_decimal(name, value)


def protection_levels(
    entry_price: Decimal,
    pip_size: Decimal,
    direction: str,
    policy: SignalOrderPolicy,
) -> tuple[Decimal | None, Decimal | None]:
    stop_distance = policy.stop_distance_pips * pip_size if policy.stop_distance_pips is not None else None
    target_distance = policy.target_distance_pips * pip_size if policy.target_distance_pips is not None else None
    long = direction == "LONG"
    stop = entry_price - stop_distance if long and stop_distance is not None else (
        entry_price + stop_distance if stop_distance is not None else None
    )
    target = entry_price + target_distance if long and target_distance is not None else (
        entry_price - target_distance if target_distance is not None else None
    )
    return stop, target
