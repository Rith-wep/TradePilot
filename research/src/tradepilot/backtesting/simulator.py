"""Deterministic event-driven H1 forex execution simulator."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from enum import IntEnum
from typing import Sequence

from tradepilot.backtesting.config import EXECUTION_MODEL_VERSION
from tradepilot.backtesting.events import (
    FillEvent,
    FillPurpose,
    OpeningQuoteEvent,
    PriceSide,
    required_price_side,
)
from tradepilot.backtesting.execution import adverse_execution, commission, stressed_price
from tradepilot.backtesting.models import TradeDirection
from tradepilot.backtesting.orders import OrderRequest, OrderState
from tradepilot.backtesting.positions import PositionState, PositionStatus
from tradepilot.backtesting.policies import FinancingModel, OrderType
from tradepilot.backtesting.signal_policy import protection_levels
from tradepilot.backtesting.simulation_models import (
    AuditKind,
    AuditValue,
    ExitReason,
    SimulationAuditRecord,
    SimulationCandidateReport,
    SimulationConfig,
    SimulationDisposition,
    SimulationResult,
    candidate_id,
)
from tradepilot.backtesting.validation import validate_fill, validate_order_configuration, validate_order_quote
from tradepilot.data.integrity import IntegrityReport
from tradepilot.data.models import Candle
from tradepilot.data.sessions import TradingSessionCalendar, classify_gaps
from tradepilot.core.canonical import canonical_json_bytes, sha256_hex
from tradepilot.strategies.models import Direction, SetupRecord


class SimulationError(ValueError):
    """Raised when verified simulation inputs or explicit policies conflict."""


class _Priority(IntEnum):
    CANDLE_COMPLETED = 10
    SIGNAL_OBSERVABLE = 20
    GAP = 22
    ORDER_EXPIRY = 25
    OPENING_QUOTE = 30


@dataclass(frozen=True, slots=True)
class _Scheduled:
    at: datetime
    priority: _Priority
    tie_key: str
    value: object


@dataclass(slots=True)
class _ActivePosition:
    state: PositionState
    entry_candle_open: datetime
    held_candles: int = 0


class _Recorder:
    def __init__(self, simulation_id: str, config: SimulationConfig) -> None:
        self.simulation_id = simulation_id
        self.config = config
        self.records: list[SimulationAuditRecord] = []

    def add(self, at: datetime, kind: AuditKind, subject: str, **details: object) -> None:
        values = tuple(
            AuditValue(name, value)  # type: ignore[arg-type]
            for name, value in sorted(details.items())
        )
        sequence = len(self.records)
        identity = sha256_hex(canonical_json_bytes({
            "simulation_id": self.simulation_id,
            "sequence": sequence,
            "occurred_at": at,
            "kind": kind,
            "subject_id": subject,
            "details": values,
        }))
        provenance = self.config.backtest.provenance
        self.records.append(SimulationAuditRecord(
            identity, sequence, at, kind, subject,
            provenance.dataset_id, provenance.dataset_checksum,
            provenance.research_report_id, self.config.configuration_id,
            self.config.backtest.execution_model_version,
            provenance.implementation_revision, values,
        ))


def _direction(value: Direction) -> TradeDirection:
    return TradeDirection(value.value)


def _ensure_precision(value: Decimal, precision: int, label: str) -> None:
    quantum = Decimal(1).scaleb(-precision)
    if value != value.quantize(quantum):
        raise SimulationError(f"{label} exceeds instrument price precision")


class EventDrivenSimulator:
    def run(
        self,
        integrity: IntegrityReport,
        report: SimulationCandidateReport,
        config: SimulationConfig,
        calendar: TradingSessionCalendar,
    ) -> SimulationResult:
        self._validate_inputs(integrity, report, config, calendar)
        candles = tuple(integrity.candles)
        simulation_id = sha256_hex(canonical_json_bytes({
            "configuration_id": config.configuration_id,
            "dataset_id": report.dataset_id,
            "report_id": report.report_id,
        }))
        recorder = _Recorder(simulation_id, config)
        scheduled = self._schedule(candles, report.signals, calendar)
        orders: list[OrderRequest] = []
        states: dict[str, OrderState] = {}
        fills: list[FillEvent] = []
        positions: list[PositionState] = []
        pending: OrderRequest | None = None
        active: _ActivePosition | None = None
        disposition = SimulationDisposition.COMPLETED
        last_open = candles[-1].timestamp
        dataset_end = last_open + timedelta(hours=1)

        index = 0
        while index < len(scheduled):
            event = scheduled[index]
            if event.at > dataset_end:
                break
            if event.priority is _Priority.SIGNAL_OBSERVABLE:
                group: list[SetupRecord] = []
                while index < len(scheduled):
                    grouped = scheduled[index]
                    if grouped.at != event.at or grouped.priority is not _Priority.SIGNAL_OBSERVABLE:
                        break
                    group.append(grouped.value)  # type: ignore[arg-type]
                    index += 1
                prior_pending = pending
                pending = self._consider_signals(
                    group, event.at, pending, report, config, recorder, orders, states
                )
                if pending is not None and pending is not prior_pending:
                    scheduled.append(_Scheduled(
                        pending.expires_at, _Priority.ORDER_EXPIRY,
                        pending.order_id, pending.order_id,
                    ))
                    scheduled[index:] = sorted(
                        scheduled[index:],
                        key=lambda item: (item.at, int(item.priority), item.tie_key),
                    )
                continue

            index += 1
            if event.priority is _Priority.CANDLE_COMPLETED:
                candle = event.value
                if not isinstance(candle, Candle):
                    raise AssertionError("scheduled completed event is not a candle")
                recorder.add(
                    event.at, AuditKind.MARKET_CANDLE_COMPLETED,
                    candle.timestamp.isoformat(), candle_open_time=candle.timestamp,
                    bid_high=candle.bid_high, bid_low=candle.bid_low, bid_close=candle.bid_close,
                    ask_high=candle.ask_high, ask_low=candle.ask_low, ask_close=candle.ask_close,
                )
                if active is not None and candle.timestamp >= active.entry_candle_open:
                    active = self._process_completed_position(
                        active, candle, event.at, candle.timestamp == last_open,
                        config, recorder, fills, positions,
                    )
            elif event.priority is _Priority.GAP:
                classification = str(event.value)
                if classification == "expected_closure":
                    if pending is not None and event.at < pending.expires_at:
                        recorder.add(event.at, AuditKind.EXPECTED_CLOSURE_SKIPPED, pending.order_id)
                else:
                    recorder.add(event.at, AuditKind.UNEXPECTED_GAP, "market-data-gap")
                    if pending is not None:
                        states[pending.order_id] = OrderState.REJECTED
                        recorder.add(
                            event.at, AuditKind.ORDER_STATE, pending.order_id,
                            previous_state=OrderState.PENDING.value,
                            state=OrderState.REJECTED.value,
                            reason="unexpected_missing_interval",
                        )
                        pending = None
                    if active is not None:
                        disposition = SimulationDisposition.INVALIDATED_UNEXPECTED_GAP
                        break
            elif event.priority is _Priority.ORDER_EXPIRY:
                order = event.value
                if isinstance(order, str) and pending is not None and pending.order_id == order:
                    states[order] = OrderState.EXPIRED
                    recorder.add(
                        event.at, AuditKind.ORDER_STATE, order,
                        previous_state=OrderState.PENDING.value,
                        state=OrderState.EXPIRED.value,
                        reason="entry_expiry_reached",
                    )
                    pending = None
            elif event.priority is _Priority.OPENING_QUOTE:
                candle = event.value
                if not isinstance(candle, Candle):
                    raise AssertionError("scheduled opening event is not a candle")
                recorder.add(
                    event.at, AuditKind.MARKET_OPENING_QUOTE,
                    candle.timestamp.isoformat(), bid_open=candle.bid_open,
                    ask_open=candle.ask_open,
                )
                # Carried protection always precedes a new entry at this opening.
                if active is not None and candle.timestamp > active.entry_candle_open:
                    active = self._process_opening_position(
                        active, candle, event.at, config, recorder, fills, positions
                    )
                if active is None and pending is not None:
                    active, pending = self._fill_entry(
                        pending, candle, event.at, config, recorder, fills, positions, states
                    )

        if (
            disposition is SimulationDisposition.COMPLETED
            and pending is not None
            and states[pending.order_id] is OrderState.PENDING
        ):
            if pending.expires_at <= dataset_end:
                # This is defensive: an in-range expiry should already be scheduled.
                states[pending.order_id] = OrderState.EXPIRED
                recorder.add(
                    pending.expires_at, AuditKind.ORDER_STATE, pending.order_id,
                    previous_state=OrderState.PENDING.value,
                    state=OrderState.EXPIRED.value,
                    reason="entry_expiry_reached",
                )
            else:
                recorder.add(
                    dataset_end, AuditKind.UNRESOLVED_END_OF_DATA, pending.order_id,
                    lifecycle_state=OrderState.PENDING.value,
                    expires_at=pending.expires_at,
                )

        return SimulationResult(
            simulation_id, config.configuration_id, disposition,
            tuple(recorder.records), tuple(orders), tuple(sorted(states.items())),
            tuple(fills), tuple(positions),
        )

    def _validate_inputs(self, integrity, report, config, calendar) -> None:
        if not integrity.valid or not integrity.candles:
            raise SimulationError("dataset must pass integrity verification and contain candles")
        provenance = config.backtest.provenance
        comparisons = (
            (integrity.dataset_id, report.dataset_id, "dataset ID"),
            (integrity.dataset_checksum, report.dataset_checksum, "dataset checksum"),
            (provenance.dataset_id, report.dataset_id, "configured dataset ID"),
            (provenance.dataset_checksum, report.dataset_checksum, "configured dataset checksum"),
            (provenance.research_report_id, report.report_id, "research report ID"),
            (provenance.strategy_name, report.strategy_name, "strategy name"),
            (provenance.strategy_version, report.strategy_version, "strategy version"),
            (provenance.configuration_fingerprint, report.configuration_fingerprint, "configuration fingerprint"),
            (config.backtest.instrument.symbol, report.instrument, "instrument"),
            (config.backtest.timeframe, report.timeframe, "timeframe"),
            (config.backtest.session_calendar_id, calendar.calendar_id, "calendar"),
            (report.session_calendar_id, calendar.calendar_id, "report calendar"),
        )
        for actual, expected, label in comparisons:
            if actual != expected:
                raise SimulationError(f"{label} provenance mismatch")
        if config.backtest.financing_policy.model is not FinancingModel.NONE:
            raise SimulationError("Step 2 supports FinancingModel.NONE only")
        if config.signal_order.quantity > config.backtest.risk_policy.max_quantity:
            raise SimulationError("signal quantity exceeds configured risk maximum")
        if config.signal_order.quantity % config.backtest.instrument.quantity_increment != 0:
            raise SimulationError("signal quantity does not align with instrument increment")

    def _schedule(self, candles, signals, calendar) -> list[_Scheduled]:
        scheduled: list[_Scheduled] = []
        for candle in candles:
            scheduled.append(_Scheduled(candle.timestamp, _Priority.OPENING_QUOTE, candle.timestamp.isoformat(), candle))
            scheduled.append(_Scheduled(
                candle.timestamp + timedelta(hours=1), _Priority.CANDLE_COMPLETED,
                candle.timestamp.isoformat(), candle,
            ))
        for setup in signals:
            scheduled.append(_Scheduled(
                setup.observable_at, _Priority.SIGNAL_OBSERVABLE, candidate_id(setup), setup
            ))
        gaps = classify_gaps(candles, calendar)
        for gap in gaps.intervals:
            scheduled.append(_Scheduled(gap.timestamp, _Priority.GAP, gap.classification, gap.classification))
        scheduled.sort(key=lambda item: (item.at, int(item.priority), item.tie_key))
        return scheduled

    def _consider_signals(self, group, at, pending, report, config, recorder, orders, states):
        identified = sorted(((candidate_id(setup), setup) for setup in group), key=lambda item: item[0])
        for identity, setup in identified:
            recorder.add(at, AuditKind.SIGNAL_CONSIDERED, identity, direction=setup.direction.value)
        if pending is not None:
            for identity, _ in identified:
                recorder.add(at, AuditKind.SIGNAL_REJECTED, identity, reason="pending_order_exists")
            return pending
        if len({setup.direction for _, setup in identified}) > 1:
            for identity, _ in identified:
                recorder.add(at, AuditKind.SIGNAL_REJECTED, identity, reason="conflicting_directions")
            return None
        selected_id, selected = identified[0]
        for identity, _ in identified[1:]:
            recorder.add(at, AuditKind.SIGNAL_REJECTED, identity, reason="same_direction_canonical_tie_break")
        order_id = sha256_hex(canonical_json_bytes({
            "configuration_id": config.configuration_id,
            "candidate_id": selected_id,
            "created_at": at,
        }))
        order = OrderRequest(
            order_id, selected_id, OrderType.MARKET_NEXT_ELIGIBLE_OPEN,
            _direction(selected.direction), selected.instrument,
            config.signal_order.quantity, selected.detection_candle_open_time,
            selected.observable_at, at, at, at + config.signal_order.entry_expiry,
            None, None, config.backtest.provenance,
        )
        validate_order_configuration(order, config.backtest)
        orders.append(order)
        states[order_id] = OrderState.PENDING
        recorder.add(at, AuditKind.ORDER_CREATED, order_id, candidate_id=selected_id, expires_at=order.expires_at)
        recorder.add(
            at, AuditKind.ORDER_STATE, order_id,
            previous_state=OrderState.CREATED.value, state=OrderState.PENDING.value,
            reason="eligible_candidate",
        )
        return order

    @staticmethod
    def _quote(candle: Candle, provenance) -> OpeningQuoteEvent:
        return OpeningQuoteEvent(
            candle.instrument.symbol, candle.timeframe, candle.timestamp, candle.timestamp,
            candle.bid_open, candle.ask_open, provenance.dataset_id, provenance.dataset_checksum,
        )

    def _fill_entry(self, order, candle, at, config, recorder, fills, positions, states):
        quote = self._quote(candle, config.backtest.provenance)
        validate_order_quote(order, quote)
        side = required_price_side(order.direction, FillPurpose.ENTRY)
        raw = candle.ask_open if side is PriceSide.ASK else candle.bid_open
        pricing = adverse_execution(raw, side, config.backtest.instrument, config.backtest.execution_policy)
        _ensure_precision(pricing.final_price, config.backtest.instrument.price_precision, "entry fill")
        fill_id = sha256_hex(canonical_json_bytes({"order_id": order.order_id, "purpose": "ENTRY", "at": at}))
        fill = FillEvent(
            fill_id, order.order_id, FillPurpose.ENTRY, order.direction, at, order.quantity,
            side, raw, pricing.spread_stress, pricing.slippage, pricing.final_price,
            commission(order.quantity, config.backtest.cost_policy), order.provenance,
            pricing.stressed_price, None, pricing.reference_price,
        )
        validate_fill(order, OrderState.PENDING, fill)
        states[order.order_id] = OrderState.FILLED
        recorder.add(
            at, AuditKind.ORDER_STATE, order.order_id,
            previous_state=OrderState.PENDING.value, state=OrderState.FILLED.value,
            reason="eligible_opening_quote",
        )
        self._record_fill(recorder, AuditKind.ENTRY_FILL, fill, None)
        stop, target = protection_levels(
            fill.execution_price, config.backtest.instrument.pip_size,
            order.direction.value, config.signal_order,
        )
        for label, level in (("stop", stop), ("target", target)):
            if level is not None:
                _ensure_precision(level, config.backtest.instrument.price_precision, label)
        opened = PositionState(
            sha256_hex(canonical_json_bytes({"entry_fill_id": fill.fill_id})),
            order.order_id, fill.fill_id, order.instrument, order.direction,
            fill.quantity, fill.execution_price, fill.filled_at,
            config.backtest.account_currency, config.backtest.instrument.quote_currency,
            stop, target,
        )
        fills.append(fill)
        positions.append(opened)
        recorder.add(
            at, AuditKind.POSITION_OPENED, opened.position_id,
            direction=opened.direction.value, entry_price=opened.entry_price,
            stop_loss=stop, take_profit=target,
        )
        return _ActivePosition(opened, candle.timestamp), None

    def _opening_trigger(self, active, candle, config):
        position = active.state
        side = required_price_side(position.direction, FillPurpose.EXIT)
        raw = candle.bid_open if side is PriceSide.BID else candle.ask_open
        stressed, _ = stressed_price(raw, side, config.backtest.instrument, config.backtest.execution_policy)
        stop = position.stop_loss
        target = position.take_profit
        long = position.direction is TradeDirection.LONG
        stop_hit = stop is not None and (stressed <= stop if long else stressed >= stop)
        target_hit = target is not None and (stressed >= target if long else stressed <= target)
        if stop_hit:
            return ExitReason.STOP_LOSS, raw, stressed, stop, None
        if target_hit:
            return ExitReason.TAKE_PROFIT, raw, stressed, target, target
        return None

    def _process_opening_position(self, active, candle, at, config, recorder, fills, positions):
        trigger = self._opening_trigger(active, candle, config)
        if trigger is None:
            return active
        reason, raw, stressed, level, conservative_reference = trigger
        reference = stressed if reason is ExitReason.STOP_LOSS else conservative_reference
        return self._close(
            active, at, raw, reason, level, reference, config, recorder, fills, positions,
            opening_stressed=stressed,
        )

    def _intrabar_trigger(self, active, candle, config):
        position = active.state
        side = required_price_side(position.direction, FillPurpose.EXIT)
        long = position.direction is TradeDirection.LONG
        stop_raw = candle.bid_low if long else candle.ask_high
        target_raw = candle.bid_high if long else candle.ask_low
        stop_stressed, _ = stressed_price(stop_raw, side, config.backtest.instrument, config.backtest.execution_policy)
        target_stressed, _ = stressed_price(target_raw, side, config.backtest.instrument, config.backtest.execution_policy)
        stop_hit = position.stop_loss is not None and (
            stop_stressed <= position.stop_loss if long else stop_stressed >= position.stop_loss
        )
        target_hit = position.take_profit is not None and (
            target_stressed >= position.take_profit if long else target_stressed <= position.take_profit
        )
        if stop_hit:
            return ExitReason.STOP_LOSS, stop_raw, stop_stressed, position.stop_loss, stop_hit and target_hit
        if target_hit:
            return ExitReason.TAKE_PROFIT, target_raw, target_stressed, position.take_profit, False
        return None

    def _process_completed_position(self, active, candle, at, final, config, recorder, fills, positions):
        trigger = self._intrabar_trigger(active, candle, config)
        if trigger is not None:
            reason, raw, stressed, level, ambiguous = trigger
            if ambiguous:
                recorder.add(
                    at, AuditKind.INTRABAR_AMBIGUITY, active.state.position_id,
                    decision="CONSERVATIVE_STOP_FIRST",
                    stop_loss=active.state.stop_loss, take_profit=active.state.take_profit,
                )
            return self._close(
                active, at, raw, reason, level, level, config, recorder, fills, positions,
                opening_stressed=stressed,
            )
        active.held_candles += 1
        if active.held_candles >= config.signal_order.max_holding_candles:
            raw = candle.bid_close if active.state.direction is TradeDirection.LONG else candle.ask_close
            return self._close(
                active, at, raw, ExitReason.TIME_EXIT, None, None,
                config, recorder, fills, positions,
            )
        if final:
            raw = candle.bid_close if active.state.direction is TradeDirection.LONG else candle.ask_close
            return self._close(
                active, at, raw, ExitReason.END_OF_DATA_EXIT, None, None,
                config, recorder, fills, positions,
            )
        return active

    def _close(self, active, at, raw, reason, level, reference, config, recorder, fills, positions, *, opening_stressed=None):
        position = active.state
        side = required_price_side(position.direction, FillPurpose.EXIT)
        pricing = adverse_execution(
            raw, side, config.backtest.instrument, config.backtest.execution_policy,
            reference_price=reference,
        )
        if opening_stressed is not None and pricing.stressed_price != opening_stressed:
            raise AssertionError("inconsistent stressed trigger quote")
        _ensure_precision(pricing.final_price, config.backtest.instrument.price_precision, "exit fill")
        recorder.add(
            at, AuditKind.EXIT_TRIGGER, position.position_id,
            reason=reason.value, raw_quote=raw, stressed_quote=pricing.stressed_price,
            trigger_level=level,
        )
        fill_id = sha256_hex(canonical_json_bytes({
            "position_id": position.position_id, "purpose": "EXIT",
            "reason": reason.value, "at": at,
        }))
        fill = FillEvent(
            fill_id, position.order_id, FillPurpose.EXIT, position.direction, at,
            position.quantity, side, raw, pricing.spread_stress, pricing.slippage,
            pricing.final_price, commission(position.quantity, config.backtest.cost_policy),
            config.backtest.provenance, pricing.stressed_price, level, pricing.reference_price,
        )
        self._record_fill(recorder, AuditKind.EXIT_FILL, fill, reason)
        closed = PositionState(
            position.position_id, position.order_id, position.entry_fill_id,
            position.instrument, position.direction, position.quantity,
            position.entry_price, position.entry_at, position.account_currency,
            position.quote_currency, position.stop_loss, position.take_profit,
            PositionStatus.CLOSED, fill.fill_id, fill.execution_price, at,
        )
        fills.append(fill)
        positions.append(closed)
        recorder.add(
            at, AuditKind.POSITION_CLOSED, position.position_id,
            reason=reason.value, exit_price=fill.execution_price,
        )
        return None

    @staticmethod
    def _record_fill(recorder, kind, fill, reason):
        recorder.add(
            fill.filled_at, kind, fill.fill_id,
            order_id=fill.order_id, purpose=fill.purpose.value,
            price_side=fill.price_side.value, raw_quote=fill.quoted_price,
            stressed_quote=fill.stressed_price, trigger_level=fill.trigger_level,
            execution_reference=fill.execution_reference_price,
            slippage=fill.slippage, final_price=fill.execution_price,
            commission=fill.commission,
            reason=reason.value if reason is not None else None,
        )
