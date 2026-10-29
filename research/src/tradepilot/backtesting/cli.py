"""Synthetic/research CLI for deterministic execution traces."""

import argparse
import json
from datetime import date, time, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Sequence

from tradepilot.backtesting.config import BACKTEST_CONFIG_SCHEMA_VERSION, EXECUTION_MODEL_VERSION, BacktestConfig
from tradepilot.backtesting.input import SimulationInputError, load_verified_candidate_report
from tradepilot.backtesting.models import BacktestProvenance, InstrumentSpec
from tradepilot.backtesting.policies import (
    AmbiguityPolicy, CommissionModel, ExecutionPolicy, FinancingModel,
    FinancingPolicy, GapStopPolicy, OpeningTargetPolicy, OrderType, RiskPolicy,
    TransactionCostPolicy, UnexpectedGapPolicy,
)
from tradepilot.backtesting.signal_policy import SignalOrderPolicy
from tradepilot.backtesting.simulation_models import SimulationConfig
from tradepilot.backtesting.simulator import EventDrivenSimulator, SimulationError
from tradepilot.data.integrity import verify_dataset
from tradepilot.data.sessions import WeeklySessionCalendar
from tradepilot.core.canonical import canonical_value
from tradepilot.reporting.validation import resolve_implementation_revision


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a deterministic synthetic forex execution trace")
    parser.add_argument("dataset", type=Path)
    parser.add_argument("report", type=Path)
    parser.add_argument("--quantity", default="10000")
    parser.add_argument("--quantity-increment", default="1000")
    parser.add_argument("--entry-expiry-hours", type=int, required=True)
    parser.add_argument("--max-holding-candles", type=int, required=True)
    parser.add_argument("--stop-pips", default=None)
    parser.add_argument("--target-pips", default=None)
    parser.add_argument("--additional-spread-pips", default="0")
    parser.add_argument("--slippage-pips", default="0")
    parser.add_argument("--timezone", default="UTC")
    parser.add_argument("--open-weekday", type=int, default=6)
    parser.add_argument("--open-time", default="22:00")
    parser.add_argument("--close-weekday", type=int, default=4)
    parser.add_argument("--close-time", default="22:00")
    parser.add_argument("--closure-date", action="append", default=[])
    parser.add_argument("--calendar-name", default="research-calendar")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    integrity = verify_dataset(args.dataset)
    if not integrity.valid or not integrity.candles:
        print(json.dumps({"error": "dataset integrity verification failed"}, sort_keys=True))
        return 1
    try:
        report = load_verified_candidate_report(args.report)
        calendar = WeeklySessionCalendar(
            args.timezone, args.open_weekday, time.fromisoformat(args.open_time),
            args.close_weekday, time.fromisoformat(args.close_time),
            frozenset(date.fromisoformat(item) for item in args.closure_date),
            args.calendar_name,
        )
        source = integrity.candles[0].instrument
        instrument = InstrumentSpec(
            source.symbol, source.base_currency, source.quote_currency,
            source.pip_size, source.price_precision, Decimal(args.quantity_increment),
        )
        provenance = BacktestProvenance(
            report.dataset_id, report.dataset_checksum, report.report_id,
            report.strategy_name, report.strategy_version,
            report.configuration_fingerprint, resolve_implementation_revision(Path.cwd()),
        )
        base = BacktestConfig(
            BACKTEST_CONFIG_SCHEMA_VERSION, EXECUTION_MODEL_VERSION, provenance,
            instrument, report.timeframe, source.quote_currency, calendar.calendar_id,
            ExecutionPolicy(
                "1", OrderType.MARKET_NEXT_ELIGIBLE_OPEN, UnexpectedGapPolicy.REJECT,
                AmbiguityPolicy.CONSERVATIVE_STOP_FIRST, GapStopPolicy.EXECUTABLE_OPEN,
                OpeningTargetPolicy.EXECUTABLE_OPEN, Decimal(args.additional_spread_pips),
                Decimal(args.slippage_pips),
            ),
            TransactionCostPolicy("1", CommissionModel.NONE, Decimal("0")),
            FinancingPolicy("1", FinancingModel.NONE),
            RiskPolicy("1", 1, Decimal(args.quantity)),
        )
        policy = SignalOrderPolicy(
            "1", Decimal(args.quantity), timedelta(hours=args.entry_expiry_hours),
            args.max_holding_candles,
            Decimal(args.stop_pips) if args.stop_pips is not None else None,
            Decimal(args.target_pips) if args.target_pips is not None else None,
        )
        result = EventDrivenSimulator().run(integrity, report, SimulationConfig(base, policy), calendar)
    except (ValueError, InvalidOperation, SimulationInputError, SimulationError) as exc:
        print(json.dumps({"error": str(exc)}, sort_keys=True))
        return 2
    print(json.dumps(canonical_value(result), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
