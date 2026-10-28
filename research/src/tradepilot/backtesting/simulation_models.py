"""Immutable deterministic simulator inputs, audit records, and results."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum

from tradepilot.backtesting.config import BacktestConfig
from tradepilot.backtesting.events import FillEvent
from tradepilot.backtesting.models import require_utc
from tradepilot.backtesting.orders import OrderRequest, OrderState
from tradepilot.backtesting.positions import PositionState
from tradepilot.backtesting.signal_policy import SignalOrderPolicy
from tradepilot.reporting.canonical import canonical_json_bytes, sha256_hex
from tradepilot.strategies.models import SetupRecord


AuditScalar = Decimal | str | int | bool | None


class AuditKind(str, Enum):
    MARKET_CANDLE_COMPLETED = "MARKET_CANDLE_COMPLETED"
    MARKET_OPENING_QUOTE = "MARKET_OPENING_QUOTE"
    SIGNAL_CONSIDERED = "SIGNAL_CONSIDERED"
    SIGNAL_REJECTED = "SIGNAL_REJECTED"
    ORDER_CREATED = "ORDER_CREATED"
    ORDER_STATE = "ORDER_STATE"
    ENTRY_FILL = "ENTRY_FILL"
    POSITION_OPENED = "POSITION_OPENED"
    EXIT_TRIGGER = "EXIT_TRIGGER"
    INTRABAR_AMBIGUITY = "INTRABAR_AMBIGUITY"
    EXIT_FILL = "EXIT_FILL"
    POSITION_CLOSED = "POSITION_CLOSED"
    EXPECTED_CLOSURE_SKIPPED = "EXPECTED_CLOSURE_SKIPPED"
    UNEXPECTED_GAP = "UNEXPECTED_GAP"
    UNRESOLVED_END_OF_DATA = "UNRESOLVED_END_OF_DATA"


class ExitReason(str, Enum):
    STOP_LOSS = "STOP_LOSS"
    TAKE_PROFIT = "TAKE_PROFIT"
    TIME_EXIT = "TIME_EXIT"
    END_OF_DATA_EXIT = "END_OF_DATA_EXIT"


class SimulationDisposition(str, Enum):
    COMPLETED = "COMPLETED"
    INVALIDATED_UNEXPECTED_GAP = "INVALIDATED_UNEXPECTED_GAP"


@dataclass(frozen=True, slots=True)
class AuditValue:
    name: str
    value: AuditScalar


@dataclass(frozen=True, slots=True)
class SimulationAuditRecord:
    event_id: str
    sequence: int
    occurred_at: datetime
    kind: AuditKind
    subject_id: str
    dataset_id: str
    dataset_checksum: str
    research_report_id: str
    backtest_configuration_id: str
    execution_model_version: str
    implementation_revision: str
    details: tuple[AuditValue, ...]

    def __post_init__(self) -> None:
        require_utc("occurred_at", self.occurred_at)
        if self.sequence < 0 or not self.event_id or not self.subject_id:
            raise ValueError("audit identity and non-negative sequence are required")


@dataclass(frozen=True, slots=True)
class SimulationCandidateReport:
    report_id: str
    dataset_id: str
    dataset_checksum: str
    instrument: str
    timeframe: str
    strategy_name: str
    strategy_version: str
    configuration_fingerprint: str
    session_calendar_id: str
    signals: tuple[SetupRecord, ...]


@dataclass(frozen=True, slots=True)
class SimulationConfig:
    backtest: BacktestConfig
    signal_order: SignalOrderPolicy

    @property
    def configuration_id(self) -> str:
        return sha256_hex(canonical_json_bytes(self))


@dataclass(frozen=True, slots=True)
class SimulationResult:
    simulation_id: str
    configuration_id: str
    disposition: SimulationDisposition
    audit_log: tuple[SimulationAuditRecord, ...]
    orders: tuple[OrderRequest, ...]
    order_states: tuple[tuple[str, OrderState], ...]
    fills: tuple[FillEvent, ...]
    positions: tuple[PositionState, ...]


def candidate_id(setup: SetupRecord) -> str:
    return sha256_hex(canonical_json_bytes(setup))
