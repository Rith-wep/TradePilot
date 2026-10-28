"""Immutable accounting, ledger, trade, metric, and report contracts."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum

from tradepilot.backtesting.models import CurrencyConversionObservation, require_currency, require_positive_decimal, require_utc


ACCOUNTING_MODEL_VERSION = "tradepilot-accounting/1.0.0"


class MetricStatus(str, Enum):
    DEFINED = "DEFINED"
    UNDEFINED_NO_TRADES = "UNDEFINED_NO_TRADES"
    UNDEFINED_NO_WINS = "UNDEFINED_NO_WINS"
    UNDEFINED_NO_LOSSES = "UNDEFINED_NO_LOSSES"
    UNDEFINED_ZERO_INITIAL_RISK = "UNDEFINED_ZERO_INITIAL_RISK"
    UNDEFINED_NONPOSITIVE_PEAK = "UNDEFINED_NONPOSITIVE_PEAK"


class ExecutionTimeKind(str, Enum):
    OPENING_BOUNDARY = "OPENING_BOUNDARY"
    CANDLE_CLOSE_BOUNDARY_MODELED = "CANDLE_CLOSE_BOUNDARY_MODELED"
    INTRABAR_INTERVAL_UNKNOWN = "INTRABAR_INTERVAL_UNKNOWN"
    INTRABAR_AMBIGUOUS = "INTRABAR_AMBIGUOUS"


class ConversionOrientation(str, Enum):
    IDENTITY = "IDENTITY"
    DIRECT = "DIRECT"
    RECIPROCAL = "RECIPROCAL"


class LedgerKind(str, Enum):
    INITIAL_BALANCE = "INITIAL_BALANCE"
    ENTRY_COMMISSION = "ENTRY_COMMISSION"
    EXIT_GROSS_PNL = "EXIT_GROSS_PNL"
    EXIT_COMMISSION = "EXIT_COMMISSION"


@dataclass(frozen=True, slots=True)
class AccountingConfig:
    account_currency: str
    initial_balance: Decimal
    commission_currency: str
    commission_currency_is_assumption: bool
    maximum_conversion_staleness: timedelta
    accounting_model_version: str = ACCOUNTING_MODEL_VERSION

    def __post_init__(self) -> None:
        require_currency("account_currency", self.account_currency)
        require_currency("commission_currency", self.commission_currency)
        require_positive_decimal("initial_balance", self.initial_balance)
        if self.maximum_conversion_staleness <= timedelta(0):
            raise ValueError("maximum_conversion_staleness must be positive")
        if self.accounting_model_version != ACCOUNTING_MODEL_VERSION:
            raise ValueError("unsupported accounting model version")


@dataclass(frozen=True, slots=True)
class ExecutionTiming:
    recognized_at: datetime
    kind: ExecutionTimeKind
    interval_start: datetime
    interval_end: datetime
    historical_execution_at: datetime | None

    def __post_init__(self) -> None:
        for name in ("recognized_at", "interval_start", "interval_end"):
            require_utc(name, getattr(self, name))
        if self.historical_execution_at is not None:
            require_utc("historical_execution_at", self.historical_execution_at)
        if self.interval_start > self.interval_end or self.recognized_at < self.interval_end:
            raise ValueError("execution timing interval is invalid")


@dataclass(frozen=True, slots=True)
class AppliedConversion:
    original_currency: str
    account_currency: str
    original_amount: Decimal
    converted_amount: Decimal
    orientation: ConversionOrientation
    applied_rate: Decimal
    valuation_at: datetime
    observation: CurrencyConversionObservation | None


@dataclass(frozen=True, slots=True)
class MetricValue:
    value: Decimal | None
    status: MetricStatus

    def __post_init__(self) -> None:
        if self.status is MetricStatus.DEFINED:
            if self.value is None or not self.value.is_finite():
                raise ValueError("defined metric requires a finite Decimal")
        elif self.value is not None:
            raise ValueError("undefined metric must not contain a value")


@dataclass(frozen=True, slots=True)
class TradeAccounting:
    position_id: str
    order_id: str
    instrument: str
    direction: str
    quantity_base: Decimal
    quote_currency: str
    account_currency: str
    entry_price: Decimal
    exit_price: Decimal
    entry_recognized_at: datetime
    exit_timing: ExecutionTiming
    exit_reason: str
    gross_pnl_quote: Decimal
    gross_pnl_account: Decimal
    entry_commission_account: Decimal
    exit_commission_account: Decimal
    net_pnl_account: Decimal
    initial_risk_account: Decimal | None
    r_multiple: MetricValue
    forced_end_of_dataset: bool
    ambiguous_intrabar: bool


@dataclass(frozen=True, slots=True)
class LedgerTransaction:
    transaction_id: str
    sequence: int
    recognized_at: datetime
    kind: LedgerKind
    subject_id: str
    original_currency: str
    original_amount: Decimal
    account_currency: str
    account_amount: Decimal
    cash_after: Decimal
    conversion: AppliedConversion


@dataclass(frozen=True, slots=True)
class EquityPoint:
    timestamp: datetime
    cash: Decimal
    unrealized_pnl: Decimal
    equity: Decimal
    peak_equity: Decimal
    drawdown_amount: Decimal
    drawdown_percentage: MetricValue
    exposure_base_units: Decimal
    exposure_account: Decimal


@dataclass(frozen=True, slots=True)
class PerformanceMetrics:
    closed_trades: int
    winning_trades: int
    losing_trades: int
    breakeven_trades: int
    win_rate: MetricValue
    average_win: MetricValue
    average_loss: MetricValue
    gross_profit: Decimal
    gross_loss: Decimal
    net_pnl: Decimal
    profit_factor: MetricValue
    expectancy: MetricValue
    maximum_drawdown: Decimal
    maximum_drawdown_percentage: MetricValue
    average_holding_seconds_lower: MetricValue
    average_holding_seconds_upper: MetricValue
    unresolved_orders: int
    forced_end_of_dataset_exits: int
    ambiguous_intrabar_exits: int


@dataclass(frozen=True, slots=True)
class AccountingContent:
    accounting_model_version: str
    dataset_id: str
    dataset_checksum: str
    research_report_id: str
    simulation_id: str
    backtest_configuration_id: str
    execution_model_version: str
    implementation_revision: str
    account_currency: str
    initial_balance: Decimal
    commission_currency: str
    commission_currency_is_assumption: bool
    used_conversion_observations: tuple[CurrencyConversionObservation, ...]
    trades: tuple[TradeAccounting, ...]
    ledger: tuple[LedgerTransaction, ...]
    equity_curve: tuple[EquityPoint, ...]
    metrics: PerformanceMetrics


@dataclass(frozen=True, slots=True)
class AccountingReport:
    report_id: str
    content: AccountingContent


@dataclass(frozen=True, slots=True)
class AccountingRun:
    report: AccountingReport
    created_at: datetime

    def __post_init__(self) -> None:
        require_utc("created_at", self.created_at)
