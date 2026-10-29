"""Deterministic backtest configuration and separate run metadata."""

from dataclasses import dataclass
from datetime import datetime

from tradepilot.backtesting.models import BacktestProvenance, InstrumentSpec, require_currency, require_utc
from tradepilot.backtesting.policies import ExecutionPolicy, FinancingPolicy, RiskPolicy, TransactionCostPolicy
from tradepilot.core.canonical import canonical_json_bytes, sha256_hex


BACKTEST_CONFIG_SCHEMA_VERSION = "tradepilot-backtest-config-v1"
EXECUTION_MODEL_VERSION = "tradepilot-execution-domain/1.0.0"


@dataclass(frozen=True, slots=True)
class BacktestConfig:
    schema_version: str
    execution_model_version: str
    provenance: BacktestProvenance
    instrument: InstrumentSpec
    timeframe: str
    account_currency: str
    session_calendar_id: str
    execution_policy: ExecutionPolicy
    cost_policy: TransactionCostPolicy
    financing_policy: FinancingPolicy
    risk_policy: RiskPolicy

    def __post_init__(self) -> None:
        if self.schema_version != BACKTEST_CONFIG_SCHEMA_VERSION:
            raise ValueError("unsupported backtest configuration schema")
        if self.execution_model_version != EXECUTION_MODEL_VERSION:
            raise ValueError("unsupported execution model version")
        if self.timeframe != "H1":
            raise ValueError("only H1 is supported")
        require_currency("account_currency", self.account_currency)
        if not self.session_calendar_id.strip():
            raise ValueError("session_calendar_id must not be empty")


@dataclass(frozen=True, slots=True)
class BacktestRun:
    configuration_id: str
    config: BacktestConfig
    created_at: datetime

    def __post_init__(self) -> None:
        if len(self.configuration_id) != 64 or any(character not in "0123456789abcdef" for character in self.configuration_id):
            raise ValueError("configuration_id must be a lowercase SHA-256 value")
        require_utc("created_at", self.created_at)


def backtest_configuration_id(config: BacktestConfig) -> str:
    """Hash deterministic assumptions; run creation time is intentionally absent."""

    return sha256_hex(canonical_json_bytes(config))
