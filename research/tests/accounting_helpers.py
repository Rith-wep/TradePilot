from dataclasses import replace
from datetime import timedelta
from decimal import Decimal

from simulator_helpers import build_context
from tradepilot.accounting.models import AccountingConfig
from tradepilot.backtesting.simulator import EventDrivenSimulator


def accounting_context(**simulation_options):
    integrity, report, simulation_config, calendar = build_context(**simulation_options)
    result = EventDrivenSimulator().run(integrity, report, simulation_config, calendar)
    config = AccountingConfig("USD", Decimal("10000"), "USD", True, timedelta(hours=24))
    return result, simulation_config, config
