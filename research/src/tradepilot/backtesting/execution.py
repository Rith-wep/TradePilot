"""Decimal bid/ask execution arithmetic without portfolio calculations."""

from dataclasses import dataclass
from decimal import Decimal

from tradepilot.backtesting.events import PriceSide
from tradepilot.backtesting.models import InstrumentSpec, require_positive_decimal
from tradepilot.backtesting.policies import CommissionModel, ExecutionPolicy, TransactionCostPolicy


@dataclass(frozen=True, slots=True)
class PriceExecution:
    raw_price: Decimal
    stressed_price: Decimal
    spread_stress: Decimal
    slippage: Decimal
    reference_price: Decimal
    final_price: Decimal


def stressed_price(raw: Decimal, side: PriceSide, instrument: InstrumentSpec, policy: ExecutionPolicy) -> tuple[Decimal, Decimal]:
    require_positive_decimal("raw_price", raw)
    stress = policy.additional_spread_pips * instrument.pip_size / Decimal(2)
    value = raw + stress if side is PriceSide.ASK else raw - stress
    require_positive_decimal("stressed_price", value)
    return value, stress


def adverse_execution(
    raw: Decimal,
    side: PriceSide,
    instrument: InstrumentSpec,
    policy: ExecutionPolicy,
    *,
    reference_price: Decimal | None = None,
) -> PriceExecution:
    stressed, stress = stressed_price(raw, side, instrument, policy)
    reference = stressed if reference_price is None else reference_price
    require_positive_decimal("execution_reference_price", reference)
    slip = policy.slippage_pips * instrument.pip_size
    final = reference + slip if side is PriceSide.ASK else reference - slip
    require_positive_decimal("final execution price", final)
    return PriceExecution(raw, stressed, stress, slip, reference, final)


def commission(quantity: Decimal, policy: TransactionCostPolicy) -> Decimal:
    if policy.commission_model is CommissionModel.NONE:
        return Decimal(0)
    if policy.commission_model is CommissionModel.FIXED:
        return policy.commission_amount
    return quantity * policy.commission_amount
