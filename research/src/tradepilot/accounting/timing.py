"""Honest execution-time classification derived from immutable audit events."""

from datetime import timedelta

from tradepilot.accounting.models import ExecutionTimeKind, ExecutionTiming
from tradepilot.backtesting.simulation_models import AuditKind, ExitReason, SimulationResult


def classify_exit_timing(result: SimulationResult, position_id: str, exit_at, reason: str) -> ExecutionTiming:
    same_time = [event for event in result.audit_log if event.occurred_at == exit_at]
    ambiguous = any(
        event.kind is AuditKind.INTRABAR_AMBIGUITY and event.subject_id == position_id
        for event in same_time
    )
    trigger = next(
        (event for event in same_time if event.kind is AuditKind.EXIT_TRIGGER and event.subject_id == position_id),
        None,
    )
    if trigger is None:
        raise ValueError("position closure has no exit trigger audit record")
    prior_kinds = [event.kind for event in same_time if event.sequence < trigger.sequence]
    if reason in (ExitReason.STOP_LOSS.value, ExitReason.TAKE_PROFIT.value):
        if AuditKind.MARKET_OPENING_QUOTE in prior_kinds and (
            not prior_kinds or prior_kinds[-1] is AuditKind.MARKET_OPENING_QUOTE
        ):
            return ExecutionTiming(
                exit_at, ExecutionTimeKind.OPENING_BOUNDARY,
                exit_at, exit_at, exit_at,
            )
        kind = ExecutionTimeKind.INTRABAR_AMBIGUOUS if ambiguous else ExecutionTimeKind.INTRABAR_INTERVAL_UNKNOWN
        return ExecutionTiming(exit_at, kind, exit_at - timedelta(hours=1), exit_at, None)
    return ExecutionTiming(
        exit_at, ExecutionTimeKind.CANDLE_CLOSE_BOUNDARY_MODELED,
        exit_at, exit_at, None,
    )
