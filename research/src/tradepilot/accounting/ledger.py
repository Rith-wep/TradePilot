"""Event-ordered cash ledger and no-look-ahead executable-side equity marks."""

from collections import defaultdict
from decimal import Decimal
from typing import Sequence

from tradepilot.accounting.conversion import convert
from tradepilot.accounting.models import (
    AccountingConfig, AppliedConversion, EquityPoint, LedgerKind,
    LedgerTransaction, MetricStatus, MetricValue,
)
from tradepilot.backtesting.events import FillPurpose, PriceSide
from tradepilot.backtesting.execution import stressed_price
from tradepilot.backtesting.models import CurrencyConversionObservation, TradeDirection
from tradepilot.backtesting.positions import PositionStatus
from tradepilot.backtesting.simulation_models import AuditKind, SimulationConfig, SimulationResult
from tradepilot.reporting.canonical import canonical_json_bytes, sha256_hex


def _details(event) -> dict[str, object]:
    return {item.name: item.value for item in event.details}


def build_ledger(
    result: SimulationResult,
    simulation_config: SimulationConfig,
    accounting_config: AccountingConfig,
    observations: Sequence[CurrencyConversionObservation],
) -> tuple[tuple[LedgerTransaction, ...], tuple[EquityPoint, ...], tuple[CurrencyConversionObservation, ...]]:
    if not result.audit_log:
        return (), (), ()
    fills = {item.fill_id: item for item in result.fills}
    if len(fills) != len(result.fills):
        raise ValueError("duplicate fills cannot be posted to the ledger")
    open_positions = {
        item.entry_fill_id: item for item in result.positions
        if item.status is PositionStatus.OPEN
    }
    events_by_time = defaultdict(list)
    for event in result.audit_log:
        events_by_time[event.occurred_at].append(event)
    cash = accounting_config.initial_balance
    ledger: list[LedgerTransaction] = []
    equity: list[EquityPoint] = []
    used: list[CurrencyConversionObservation] = []
    active: dict[str, tuple[object, object]] = {}
    latest_bid: Decimal | None = None
    latest_ask: Decimal | None = None
    peak = accounting_config.initial_balance

    identity = convert(
        accounting_config.initial_balance, accounting_config.account_currency,
        accounting_config.account_currency, min(events_by_time), observations,
        accounting_config.maximum_conversion_staleness,
    )
    ledger.append(_transaction(
        0, min(events_by_time), LedgerKind.INITIAL_BALANCE, "account",
        accounting_config.account_currency, accounting_config.initial_balance,
        accounting_config.account_currency, accounting_config.initial_balance,
        cash, identity,
    ))

    for timestamp in sorted(events_by_time):
        for event in sorted(events_by_time[timestamp], key=lambda item: item.sequence):
            details = _details(event)
            if event.kind is AuditKind.MARKET_OPENING_QUOTE:
                latest_bid = Decimal(str(details["bid_open"]))
                latest_ask = Decimal(str(details["ask_open"]))
            elif event.kind is AuditKind.MARKET_CANDLE_COMPLETED:
                latest_bid = Decimal(str(details["bid_close"]))
                latest_ask = Decimal(str(details["ask_close"]))
            elif event.kind is AuditKind.ENTRY_FILL:
                fill = fills[event.subject_id]
                position = open_positions.get(fill.fill_id)
                if position is None:
                    raise ValueError("entry fill has no open-position snapshot")
                conversion = convert(
                    fill.commission, accounting_config.commission_currency,
                    accounting_config.account_currency, timestamp, observations,
                    accounting_config.maximum_conversion_staleness,
                )
                if conversion.observation is not None:
                    used.append(conversion.observation)
                account_amount = -conversion.converted_amount
                cash += account_amount
                ledger.append(_transaction(
                    len(ledger), timestamp, LedgerKind.ENTRY_COMMISSION, fill.fill_id,
                    accounting_config.commission_currency, -fill.commission,
                    accounting_config.account_currency, account_amount, cash, conversion,
                ))
                active[fill.order_id] = (fill, position)
            elif event.kind is AuditKind.EXIT_FILL:
                fill = fills[event.subject_id]
                if fill.order_id not in active:
                    raise ValueError("exit fill has no active entry")
                entry, position = active[fill.order_id]
                price_difference = (
                    fill.execution_price - entry.execution_price
                    if fill.direction is TradeDirection.LONG
                    else entry.execution_price - fill.execution_price
                )
                gross_quote = price_difference * fill.quantity
                gross_conversion = convert(
                    gross_quote, simulation_config.backtest.instrument.quote_currency,
                    accounting_config.account_currency, timestamp, observations,
                    accounting_config.maximum_conversion_staleness,
                )
                if gross_conversion.observation is not None:
                    used.append(gross_conversion.observation)
                cash += gross_conversion.converted_amount
                ledger.append(_transaction(
                    len(ledger), timestamp, LedgerKind.EXIT_GROSS_PNL, fill.fill_id,
                    simulation_config.backtest.instrument.quote_currency, gross_quote,
                    accounting_config.account_currency, gross_conversion.converted_amount,
                    cash, gross_conversion,
                ))
                commission_conversion = convert(
                    fill.commission, accounting_config.commission_currency,
                    accounting_config.account_currency, timestamp, observations,
                    accounting_config.maximum_conversion_staleness,
                )
                if commission_conversion.observation is not None:
                    used.append(commission_conversion.observation)
                commission_amount = -commission_conversion.converted_amount
                cash += commission_amount
                ledger.append(_transaction(
                    len(ledger), timestamp, LedgerKind.EXIT_COMMISSION, fill.fill_id,
                    accounting_config.commission_currency, -fill.commission,
                    accounting_config.account_currency, commission_amount, cash,
                    commission_conversion,
                ))
                del active[fill.order_id]

        unrealized = Decimal(0)
        exposure_units = Decimal(0)
        exposure_account = Decimal(0)
        for entry, position in active.values():
            if latest_bid is None or latest_ask is None:
                raise ValueError("open position cannot be valued without an available quote")
            side = PriceSide.BID if entry.direction is TradeDirection.LONG else PriceSide.ASK
            raw_mark = latest_bid if side is PriceSide.BID else latest_ask
            mark, _ = stressed_price(
                raw_mark, side, simulation_config.backtest.instrument,
                simulation_config.backtest.execution_policy,
            )
            quote_unrealized = (
                (mark - entry.execution_price) * entry.quantity
                if entry.direction is TradeDirection.LONG
                else (entry.execution_price - mark) * entry.quantity
            )
            pnl_conversion = convert(
                quote_unrealized, simulation_config.backtest.instrument.quote_currency,
                accounting_config.account_currency, timestamp, observations,
                accounting_config.maximum_conversion_staleness,
            )
            notional_conversion = convert(
                entry.quantity * mark, simulation_config.backtest.instrument.quote_currency,
                accounting_config.account_currency, timestamp, observations,
                accounting_config.maximum_conversion_staleness,
            )
            for conversion in (pnl_conversion, notional_conversion):
                if conversion.observation is not None:
                    used.append(conversion.observation)
            unrealized += pnl_conversion.converted_amount
            exposure_units += entry.quantity
            exposure_account += abs(notional_conversion.converted_amount)
        current_equity = cash + unrealized
        peak = max(peak, current_equity)
        drawdown = peak - current_equity
        percentage = (
            MetricValue(drawdown / peak, MetricStatus.DEFINED)
            if peak > 0 else MetricValue(None, MetricStatus.UNDEFINED_NONPOSITIVE_PEAK)
        )
        equity.append(EquityPoint(
            timestamp, cash, unrealized, current_equity, peak, drawdown,
            percentage, exposure_units, exposure_account,
        ))
    unique_used = tuple(sorted(set(used), key=lambda item: (
        item.observed_at, item.base_currency, item.quote_currency,
        item.source, item.dataset_id, item.dataset_checksum,
    )))
    return tuple(ledger), tuple(equity), unique_used


def _transaction(sequence, at, kind, subject, original_currency, original_amount, account_currency, account_amount, cash, conversion):
    identity = sha256_hex(canonical_json_bytes({
        "sequence": sequence, "recognized_at": at, "kind": kind,
        "subject_id": subject, "original_currency": original_currency,
        "original_amount": original_amount, "account_amount": account_amount,
    }))
    return LedgerTransaction(
        identity, sequence, at, kind, subject, original_currency,
        original_amount, account_currency, account_amount, cash, conversion,
    )
