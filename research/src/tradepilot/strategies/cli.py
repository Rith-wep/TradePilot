"""Run deterministic candidate strategies on an integrity-verified snapshot."""

import argparse
import json
from dataclasses import asdict
from datetime import date, time
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Sequence

from tradepilot.data.integrity import verify_dataset
from tradepilot.data.sessions import WeeklySessionCalendar
from tradepilot.indicators import atr, ema, rsi
from tradepilot.strategies.base import StrategyInputError
from tradepilot.strategies.breakout import BreakoutConfig, PriceRangeBreakoutStrategy
from tradepilot.strategies.models import StrategyIndicators
from tradepilot.strategies.pullback import EmaRsiPullbackStrategy, PullbackConfig


def _json_default(value: object) -> object:
    if isinstance(value, Decimal):
        return format(value, "f")
    raise TypeError(f"cannot serialize {type(value).__name__}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Detect research candidate setups")
    parser.add_argument("path", type=Path, help="dataset root or immutable snapshot")
    parser.add_argument("strategy", choices=("breakout", "pullback"))
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
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    integrity = verify_dataset(args.path)
    if not integrity.valid:
        print(json.dumps({"error": "dataset integrity verification failed", "integrity": integrity.to_dict()}, indent=2, sort_keys=True))
        return 1
    try:
        calendar = WeeklySessionCalendar(
            timezone_name=args.timezone,
            open_weekday=args.open_weekday,
            open_time=time.fromisoformat(args.open_time),
            close_weekday=args.close_weekday,
            close_time=time.fromisoformat(args.close_time),
            closure_dates=frozenset(date.fromisoformat(value) for value in args.closure_date),
            name="strategy-calendar",
        )
        if args.strategy == "breakout":
            threshold = Decimal(args.minimum_breakout_atr) if args.minimum_breakout_atr is not None else None
            config = BreakoutConfig(
                lookback=args.lookback,
                price_basis=args.price_basis,
                atr_period=args.atr_period,
                minimum_breakout_atr=threshold,
            )
            strategy = PriceRangeBreakoutStrategy(config)
            indicators = StrategyIndicators(
                atr=atr(integrity.candles, config.atr_period, config.price_basis)
                if threshold is not None else None
            )
        else:
            config = PullbackConfig(
                ema_period=args.ema_period,
                rsi_period=args.rsi_period,
                atr_period=args.atr_period,
                price_basis=args.price_basis,
            )
            strategy = EmaRsiPullbackStrategy(config)
            indicators = StrategyIndicators(
                ema=ema(integrity.candles, config.ema_period, config.price_basis),
                rsi=rsi(integrity.candles, config.rsi_period, config.price_basis),
                atr=atr(integrity.candles, config.atr_period, config.price_basis),
            )
        setups = strategy.detect(integrity.candles, indicators, calendar)
    except (ValueError, InvalidOperation, StrategyInputError) as exc:
        print(json.dumps({"error": str(exc)}, sort_keys=True))
        return 2
    print(json.dumps({
        "dataset_id": integrity.dataset_id,
        "strategy_name": strategy.name,
        "strategy_version": strategy.version,
        "configuration": asdict(config),
        "candidate_count": len(setups),
        "setups": [setup.to_dict() for setup in setups],
    }, default=_json_default, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

