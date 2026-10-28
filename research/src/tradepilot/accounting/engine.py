"""Accounting orchestration over immutable simulator results."""

from typing import Sequence

from tradepilot.accounting.ledger import build_ledger
from tradepilot.accounting.metrics import calculate_metrics
from tradepilot.accounting.models import ACCOUNTING_MODEL_VERSION, AccountingConfig, AccountingContent, AccountingReport
from tradepilot.accounting.reporting import build_accounting_report
from tradepilot.accounting.trades import reconstruct_trades
from tradepilot.backtesting.models import CurrencyConversionObservation
from tradepilot.backtesting.simulation_models import SimulationConfig, SimulationResult


class AccountingError(ValueError):
    pass


def build_accounting(
    result: SimulationResult,
    simulation_config: SimulationConfig,
    config: AccountingConfig,
    observations: Sequence[CurrencyConversionObservation] = (),
) -> AccountingReport:
    if result.configuration_id != simulation_config.configuration_id:
        raise AccountingError("simulation/backtest configuration provenance mismatch")
    provenance = simulation_config.backtest.provenance
    first_audit = result.audit_log[0] if result.audit_log else None
    if first_audit is not None and (
        first_audit.dataset_id != provenance.dataset_id
        or first_audit.dataset_checksum != provenance.dataset_checksum
        or first_audit.research_report_id != provenance.research_report_id
    ):
        raise AccountingError("simulation audit provenance mismatch")
    source_currency = getattr(simulation_config.backtest.cost_policy, "commission_currency", None)
    if source_currency is None:
        if not config.commission_currency_is_assumption:
            raise AccountingError("commission currency must be labeled as an explicit assumption")
    elif source_currency != config.commission_currency:
        raise AccountingError("commission currency conflicts with simulator cost policy")
    trades, trade_observations = reconstruct_trades(result, simulation_config, config, observations)
    ledger, equity, ledger_observations = build_ledger(result, simulation_config, config, observations)
    metrics = calculate_metrics(trades, equity, result)
    used = tuple(sorted(set(trade_observations + ledger_observations), key=lambda item: (
        item.observed_at, item.base_currency, item.quote_currency,
        item.source, item.dataset_id, item.dataset_checksum,
    )))
    content = AccountingContent(
        ACCOUNTING_MODEL_VERSION, provenance.dataset_id, provenance.dataset_checksum,
        provenance.research_report_id, result.simulation_id, result.configuration_id,
        simulation_config.backtest.execution_model_version,
        provenance.implementation_revision, config.account_currency,
        config.initial_balance, config.commission_currency,
        config.commission_currency_is_assumption, used, trades, ledger,
        equity, metrics,
    )
    return build_accounting_report(content)
