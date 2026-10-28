"""Historical, timestamp-safe direct and reciprocal currency conversion."""

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Sequence

from tradepilot.accounting.models import AppliedConversion, ConversionOrientation
from tradepilot.backtesting.models import CurrencyConversionObservation, require_currency, require_utc


class ConversionError(ValueError):
    pass


def convert(
    amount: Decimal,
    original_currency: str,
    account_currency: str,
    valuation_at: datetime,
    observations: Sequence[CurrencyConversionObservation],
    maximum_staleness: timedelta,
) -> AppliedConversion:
    if not isinstance(amount, Decimal) or not amount.is_finite():
        raise ConversionError("conversion amount must be a finite Decimal")
    require_currency("original_currency", original_currency)
    require_currency("account_currency", account_currency)
    require_utc("valuation_at", valuation_at)
    if original_currency == account_currency:
        return AppliedConversion(
            original_currency, account_currency, amount, amount,
            ConversionOrientation.IDENTITY, Decimal(1), valuation_at, None,
        )
    eligible = [
        item for item in observations
        if {item.base_currency, item.quote_currency} == {original_currency, account_currency}
        and item.observed_at <= valuation_at
        and valuation_at - item.observed_at <= maximum_staleness
    ]
    if not eligible:
        raise ConversionError("no eligible non-stale conversion observation")
    latest_at = max(item.observed_at for item in eligible)
    latest = [item for item in eligible if item.observed_at == latest_at]
    unique = set(latest)
    if len(unique) != 1:
        raise ConversionError("conflicting conversion observations at latest timestamp")
    observation = latest[0]
    if observation.base_currency == original_currency:
        orientation = ConversionOrientation.DIRECT
        converted = amount * observation.rate
        applied_rate = observation.rate
    else:
        orientation = ConversionOrientation.RECIPROCAL
        converted = amount / observation.rate
        applied_rate = Decimal(1) / observation.rate
    return AppliedConversion(
        original_currency, account_currency, amount, converted, orientation,
        applied_rate, valuation_at, observation,
    )
