"""Strict trade reconstruction and quote/account-currency P&L calculations."""

from collections import Counter, defaultdict
from decimal import Decimal
from typing import Sequence

from tradepilot.accounting.conversion import convert
from tradepilot.accounting.models import AccountingConfig, MetricStatus, MetricValue, TradeAccounting
from tradepilot.accounting.timing import classify_exit_timing
from tradepilot.backtesting.events import FillPurpose
from tradepilot.backtesting.models import CurrencyConversionObservation, TradeDirection
from tradepilot.backtesting.positions import PositionStatus
from tradepilot.backtesting.simulation_models import AuditKind, ExitReason, SimulationConfig, SimulationResult


class TradeReconstructionError(ValueError):
    pass


def _details(event) -> dict[str, object]:
    return {item.name: item.value for item in event.details}


def reconstruct_trades(
    result: SimulationResult,
    simulation_config: SimulationConfig,
    accounting_config: AccountingConfig,
    observations: Sequence[CurrencyConversionObservation],
) -> tuple[tuple[TradeAccounting, ...], tuple[object, ...]]:
    fill_counts = Counter(fill.fill_id for fill in result.fills)
    if any(count != 1 for count in fill_counts.values()):
        raise TradeReconstructionError("duplicate fill identifiers are not supported")
    fills_by_order = defaultdict(list)
    for fill in result.fills:
        fills_by_order[fill.order_id].append(fill)
    positions_by_id = defaultdict(list)
    for position in result.positions:
        positions_by_id[position.position_id].append(position)
    used_conversions: list[object] = []
    trades: list[TradeAccounting] = []
    instrument = simulation_config.backtest.instrument

    for position_id, snapshots in positions_by_id.items():
        opened = [item for item in snapshots if item.status is PositionStatus.OPEN]
        closed = [item for item in snapshots if item.status is PositionStatus.CLOSED]
        if len(opened) != 1 or len(closed) > 1:
            raise TradeReconstructionError("position lifecycle must contain one open and at most one close")
        if not closed:
            continue
        open_position, closed_position = opened[0], closed[0]
        if (
            open_position.instrument != instrument.symbol
            or closed_position.instrument != instrument.symbol
            or open_position.direction is not closed_position.direction
            or open_position.quantity != closed_position.quantity
        ):
            raise TradeReconstructionError("position instrument, direction, or quantity mismatch")
        fills = fills_by_order[open_position.order_id]
        entries = [item for item in fills if item.purpose is FillPurpose.ENTRY]
        exits = [item for item in fills if item.purpose is FillPurpose.EXIT]
        if len(entries) != 1 or len(exits) != 1:
            raise TradeReconstructionError("partial or multiple fills are unsupported")
        entry, exit_fill = entries[0], exits[0]
        if entry.provenance != simulation_config.backtest.provenance or exit_fill.provenance != simulation_config.backtest.provenance:
            raise TradeReconstructionError("fill provenance does not match simulation configuration")
        if (
            entry.quantity != exit_fill.quantity
            or entry.quantity != open_position.quantity
            or entry.direction is not exit_fill.direction
            or entry.direction is not open_position.direction
        ):
            raise TradeReconstructionError("fill quantity or direction mismatch")
        if exit_fill.filled_at < entry.filled_at:
            raise TradeReconstructionError("exit recognition precedes entry")
        reason_event = next((
            event for event in result.audit_log
            if event.kind is AuditKind.POSITION_CLOSED and event.subject_id == position_id
        ), None)
        if reason_event is None:
            raise TradeReconstructionError("closed position lacks closure audit provenance")
        reason = str(_details(reason_event)["reason"])
        timing = classify_exit_timing(result, position_id, exit_fill.filled_at, reason)
        price_difference = (
            exit_fill.execution_price - entry.execution_price
            if entry.direction is TradeDirection.LONG
            else entry.execution_price - exit_fill.execution_price
        )
        gross_quote = price_difference * entry.quantity
        gross_conversion = convert(
            gross_quote, instrument.quote_currency, accounting_config.account_currency,
            exit_fill.filled_at, observations, accounting_config.maximum_conversion_staleness,
        )
        entry_commission = convert(
            entry.commission, accounting_config.commission_currency,
            accounting_config.account_currency, entry.filled_at, observations,
            accounting_config.maximum_conversion_staleness,
        )
        exit_commission = convert(
            exit_fill.commission, accounting_config.commission_currency,
            accounting_config.account_currency, exit_fill.filled_at, observations,
            accounting_config.maximum_conversion_staleness,
        )
        for conversion in (gross_conversion, entry_commission, exit_commission):
            if conversion.observation is not None:
                used_conversions.append(conversion.observation)
        net = gross_conversion.converted_amount - entry_commission.converted_amount - exit_commission.converted_amount
        risk_account = None
        if open_position.stop_loss is not None:
            risk_per_unit = (
                entry.execution_price - open_position.stop_loss
                if entry.direction is TradeDirection.LONG
                else open_position.stop_loss - entry.execution_price
            )
            if risk_per_unit > 0:
                risk_conversion = convert(
                    risk_per_unit * entry.quantity, instrument.quote_currency,
                    accounting_config.account_currency, entry.filled_at, observations,
                    accounting_config.maximum_conversion_staleness,
                )
                risk_account = risk_conversion.converted_amount
                if risk_conversion.observation is not None:
                    used_conversions.append(risk_conversion.observation)
        r_multiple = (
            MetricValue(net / risk_account, MetricStatus.DEFINED)
            if risk_account is not None and risk_account > 0
            else MetricValue(None, MetricStatus.UNDEFINED_ZERO_INITIAL_RISK)
        )
        ambiguous = timing.kind.value == "INTRABAR_AMBIGUOUS"
        trades.append(TradeAccounting(
            position_id, entry.order_id, open_position.instrument,
            entry.direction.value, entry.quantity, instrument.quote_currency,
            accounting_config.account_currency, entry.execution_price,
            exit_fill.execution_price, entry.filled_at, timing, reason,
            gross_quote, gross_conversion.converted_amount,
            entry_commission.converted_amount, exit_commission.converted_amount,
            net, risk_account, r_multiple,
            reason == ExitReason.END_OF_DATA_EXIT.value, ambiguous,
        ))
    trades.sort(key=lambda item: (item.entry_recognized_at, item.position_id))
    unique_used = tuple(sorted(set(used_conversions), key=lambda item: (
        item.observed_at, item.base_currency, item.quote_currency, item.source,
        item.dataset_id, item.dataset_checksum,
    )))
    return tuple(trades), unique_used
