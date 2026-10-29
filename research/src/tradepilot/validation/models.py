"""Immutable chronological-validation and research-governance contracts."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum

from tradepilot.accounting.models import MetricStatus, MetricValue
from tradepilot.backtesting.models import require_utc


VALIDATION_MODEL_VERSION = "tradepilot-validation/1.0.0"


class PartitionName(str, Enum):
    TRAINING = "TRAINING"
    VALIDATION = "VALIDATION"
    LOCKED_TEST = "LOCKED_TEST"


class EvaluationStatus(str, Enum):
    ELIGIBLE = "ELIGIBLE"
    INSUFFICIENT_TRADES = "INSUFFICIENT_TRADES"
    ZERO_TRADES = "ZERO_TRADES"
    FAILED = "FAILED"


class UncertaintyStatus(str, Enum):
    DEFINED = "DEFINED"
    INSUFFICIENT_SAMPLE = "INSUFFICIENT_SAMPLE"


@dataclass(frozen=True, slots=True)
class ChronologicalPartition:
    name: PartitionName
    start: datetime
    end: datetime
    start_index: int
    end_index: int
    candle_count: int
    partition_id: str

    def __post_init__(self) -> None:
        require_utc("start", self.start)
        require_utc("end", self.end)
        if self.start >= self.end or self.end_index <= self.start_index:
            raise ValueError("partition must be a non-empty half-open interval")
        if self.candle_count != self.end_index - self.start_index:
            raise ValueError("partition candle count does not match indexes")


@dataclass(frozen=True, slots=True)
class PartitionPolicy:
    version: str = "chronological-candle-count-60-20-20/v1"
    training_fraction: Decimal = Decimal("0.60")
    validation_fraction: Decimal = Decimal("0.20")


@dataclass(frozen=True, slots=True)
class WalkForwardPolicy:
    initial_training_candles: int
    validation_candles: int
    step_candles: int
    minimum_fold_trades: int = 10
    version: str = "expanding-nonoverlap/v1"

    def __post_init__(self) -> None:
        if min(self.initial_training_candles, self.validation_candles, self.step_candles) <= 0:
            raise ValueError("walk-forward candle counts must be positive")
        if self.step_candles < self.validation_candles:
            raise ValueError("overlapping evaluation windows are not allowed")
        if self.minimum_fold_trades < 0:
            raise ValueError("minimum fold trades must not be negative")


@dataclass(frozen=True, slots=True)
class WalkForwardFold:
    fold_index: int
    training: ChronologicalPartition
    validation: ChronologicalPartition
    fold_id: str


@dataclass(frozen=True, slots=True)
class ParameterDeclaration:
    strategy_name: str
    strategy_version: str
    configuration_fingerprint: str
    parameters: tuple[tuple[str, Decimal | str | int | bool | None], ...]


@dataclass(frozen=True, slots=True)
class ScenarioEvaluation:
    scenario_id: str
    scenario_name: str
    simulation_id: str
    accounting_report_id: str
    trade_count: int
    expectancy: MetricValue
    net_pnl: Decimal
    maximum_drawdown: Decimal
    forced_exits: int
    ambiguous_exits: int
    unresolved_orders: int


@dataclass(frozen=True, slots=True)
class ConfigurationEvaluation:
    configuration: ParameterDeclaration
    partition_id: str
    scenarios: tuple[ScenarioEvaluation, ...]
    status: EvaluationStatus
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SelectionDecision:
    selection_policy_id: str
    selected_configuration_fingerprint: str | None
    eligible: tuple[str, ...]
    rejected: tuple[tuple[str, str], ...]
    decision_id: str


@dataclass(frozen=True, slots=True)
class BootstrapInterval:
    status: UncertaintyStatus
    lower: Decimal | None
    upper: Decimal | None
    sample_count: int
    block_length: int
    resamples: int


@dataclass(frozen=True, slots=True)
class StressDegradation:
    scenario_name: str
    absolute_expectancy_change: MetricValue
    relative_expectancy_change: MetricValue


@dataclass(frozen=True, slots=True)
class RobustnessSummary:
    fold_count: int
    positive_folds: int
    zero_trade_folds: int
    insufficient_folds: int
    fraction_positive: MetricValue
    median_expectancy: MetricValue
    expectancy_range: MetricValue
    stress_degradation: tuple[StressDegradation, ...]


@dataclass(frozen=True, slots=True)
class LockedTestAuthorization:
    authorization_id: str
    dataset_id: str
    dataset_checksum: str
    locked_partition_id: str
    strategy_name: str
    strategy_version: str
    selected_configuration_fingerprint: str
    selection_decision_id: str
    cost_scenario_ids: tuple[str, ...]
    implementation_revision: str


@dataclass(frozen=True, slots=True)
class LockedTestEvaluation:
    authorization_id: str
    result_id: str
    scenario_results: tuple[ScenarioEvaluation, ...]


@dataclass(frozen=True, slots=True)
class ValidationContent:
    model_version: str
    dataset_id: str
    dataset_checksum: str
    strategy_name: str
    strategy_version: str
    implementation_revision: str
    partitions: tuple[ChronologicalPartition, ...]
    folds: tuple[WalkForwardFold, ...]
    configurations: tuple[ParameterDeclaration, ...]
    evaluations: tuple[ConfigurationEvaluation, ...]
    selection: SelectionDecision
    locked_authorization: LockedTestAuthorization | None
    locked_evaluation: LockedTestEvaluation | None
    robustness: RobustnessSummary
    bootstrap: BootstrapInterval
    warnings: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ValidationReport:
    report_id: str
    content: ValidationContent
