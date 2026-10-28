"""Generate and verify reproducible candidate-signal research reports."""

import argparse
import json
from dataclasses import asdict
from datetime import date, datetime, time, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Sequence

from tradepilot.data.integrity import verify_dataset
from tradepilot.data.sessions import WeeklySessionCalendar
from tradepilot.indicators import atr, ema, rsi
from tradepilot.reporting.models import IndicatorParameter
from tradepilot.reporting.storage import ReportStorage, ReportStorageError, verify_report
from tradepilot.reporting.validation import (
    ReportValidationError,
    build_research_run,
    resolve_implementation_revision,
)
from tradepilot.strategies.base import StrategyInputError, configuration_fingerprint
from tradepilot.strategies.breakout import BreakoutConfig, PriceRangeBreakoutStrategy
from tradepilot.strategies.models import StrategyIndicators
from tradepilot.strategies.pullback import EmaRsiPullbackStrategy, PullbackConfig


def _calendar(args: argparse.Namespace) -> WeeklySessionCalendar:
    return WeeklySessionCalendar(
        timezone_name=args.timezone,
        open_weekday=args.open_weekday,
        open_time=time.fromisoformat(args.open_time),
        close_weekday=args.close_weekday,
        close_time=time.fromisoformat(args.close_time),
        closure_dates=frozenset(date.fromisoformat(value) for value in args.closure_date),
        name="research-calendar",
    )


def _add_strategy_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("path", type=Path)
    parser.add_argument("strategy", choices=("breakout", "pullback"))
    parser.add_argument("--output", type=Path, default=Path("reports"))
    parser.add_argument("--price-basis", choices=("bid", "ask", "mid"), default="mid")
    parser.add_argument("--lookback", type=int, default=20)
    parser.add_argument("--minimum-breakout-atr", default=None)
    parser.add_argument("--ema-period", type=int, default=200)
    parser.add_argument("--rsi-period", type=int, default=14)
    parser.add_argument("--atr-period", type=int, default=14)
    parser.add_argument("--timezone", default="UTC")
    parser.add_argument("--open-weekday", type=int, default=6)
    parser.add_argument("--open-time", default="22:00")
    parser.add_argument("--close-weekday", type=int, default=4)
    parser.add_argument("--close-time", default="22:00")
    parser.add_argument("--closure-date", action="append", default=[])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate or verify candidate-signal research reports")
    subparsers = parser.add_subparsers(dest="command", required=True)
    _add_strategy_arguments(subparsers.add_parser("generate"))
    verify = subparsers.add_parser("verify")
    verify.add_argument("path", type=Path)
    return parser


def _generate(args: argparse.Namespace) -> int:
    integrity = verify_dataset(args.path)
    if not integrity.valid:
        print(json.dumps({"error": "dataset integrity verification failed", "integrity": integrity.to_dict()}, indent=2, sort_keys=True))
        return 1
    try:
        calendar = _calendar(args)
        if args.strategy == "breakout":
            threshold = Decimal(args.minimum_breakout_atr) if args.minimum_breakout_atr is not None else None
            config = BreakoutConfig(
                lookback=args.lookback, price_basis=args.price_basis,
                atr_period=args.atr_period, minimum_breakout_atr=threshold,
            )
            strategy = PriceRangeBreakoutStrategy(config)
            atr_series = atr(integrity.candles, config.atr_period, config.price_basis) if threshold is not None else None
            supplied = StrategyIndicators(atr=atr_series)
            parameters = (
                (IndicatorParameter("ATR", config.atr_period, config.price_basis),)
                if threshold is not None else ()
            )
        else:
            config = PullbackConfig(
                ema_period=args.ema_period, rsi_period=args.rsi_period,
                atr_period=args.atr_period, price_basis=args.price_basis,
            )
            strategy = EmaRsiPullbackStrategy(config)
            supplied = StrategyIndicators(
                ema=ema(integrity.candles, config.ema_period, config.price_basis),
                rsi=rsi(integrity.candles, config.rsi_period, config.price_basis),
                atr=atr(integrity.candles, config.atr_period, config.price_basis),
            )
            parameters = (
                IndicatorParameter("EMA", config.ema_period, config.price_basis),
                IndicatorParameter("RSI", config.rsi_period, config.price_basis),
                IndicatorParameter("ATR", config.atr_period, config.price_basis),
            )
        fingerprint = configuration_fingerprint(strategy.name, strategy.version, config, calendar.calendar_id)
        setups = strategy.detect(integrity.candles, supplied, calendar)
        revision = resolve_implementation_revision(Path.cwd())
        run = build_research_run(
            integrity,
            strategy_name=strategy.name,
            strategy_version=strategy.version,
            configuration_fingerprint=fingerprint,
            strategy_configuration=config,
            indicator_parameters=parameters,
            session_calendar_id=calendar.calendar_id,
            reject_unexpected_gaps=config.reject_unexpected_gaps,
            setups=setups,
            created_at=datetime.now(timezone.utc),
            implementation_revision=revision,
        )
        stored = ReportStorage(args.output).save(run)
    except (ValueError, InvalidOperation, StrategyInputError, ReportValidationError, ReportStorageError) as exc:
        print(json.dumps({"error": str(exc)}, sort_keys=True))
        return 2
    print(json.dumps({
        "dataset_id": integrity.dataset_id,
        "dataset_checksum": integrity.dataset_checksum,
        "strategy_name": strategy.name,
        "strategy_version": strategy.version,
        "configuration": asdict(config),
        "configuration_fingerprint": fingerprint,
        "implementation_revision": revision,
        "report_id": stored.report_id,
        "signal_count": len(setups),
        "report_path": str(stored.report_path),
        "run_metadata_path": str(stored.run_metadata_path),
        "reused": stored.reused,
    }, default=str, indent=2, sort_keys=True))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "verify":
        verification = verify_report(args.path)
        print(json.dumps(verification.to_dict(), indent=2, sort_keys=True))
        return 0 if verification.valid else 1
    return _generate(args)


if __name__ == "__main__":
    raise SystemExit(main())

