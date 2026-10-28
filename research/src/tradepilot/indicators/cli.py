"""Reproducible indicator example over an integrity-verified snapshot."""

import argparse
import json
from pathlib import Path
from typing import Sequence

from tradepilot.data.integrity import verify_dataset
from tradepilot.indicators.core import IndicatorInputError, atr, ema, rsi


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Calculate indicators from an immutable TradePilot dataset")
    parser.add_argument("path", type=Path, help="dataset root or immutable snapshot directory")
    parser.add_argument("--ema-period", type=int, default=3)
    parser.add_argument("--rsi-period", type=int, default=3)
    parser.add_argument("--atr-period", type=int, default=3)
    parser.add_argument("--price-basis", choices=("bid", "ask", "mid"), default="mid")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = verify_dataset(args.path)
    if not report.valid:
        print(json.dumps({"error": "dataset integrity verification failed", "integrity": report.to_dict()}, indent=2, sort_keys=True))
        return 1
    try:
        series = (
            ema(report.candles, args.ema_period, args.price_basis),
            rsi(report.candles, args.rsi_period, args.price_basis),
            atr(report.candles, args.atr_period, args.price_basis),
        )
    except IndicatorInputError as exc:
        print(json.dumps({"error": str(exc)}, sort_keys=True))
        return 2
    print(json.dumps({
        "dataset_id": report.dataset_id,
        "instrument": report.instrument,
        "timeframe": report.timeframe,
        "completed_candle_count": len(report.candles),
        "indicators": [item.to_dict() for item in series],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

