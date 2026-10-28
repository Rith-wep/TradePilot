"""Command-line interface for deterministic candle quality reports."""

import argparse
import json
from decimal import Decimal
from pathlib import Path
from typing import Sequence

from tradepilot.data.csv_loader import CandleLoadError, load_candles_csv
from tradepilot.data.models import Instrument
from tradepilot.data.validation import validate_candles


EURUSD = Instrument("EURUSD", "EUR", "USD", Decimal("0.0001"), 5)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate canonical TradePilot H1 candles")
    parser.add_argument("path", type=Path, help="path to canonical candle CSV")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        candles = load_candles_csv(args.path, EURUSD)
    except CandleLoadError as exc:
        print(json.dumps({"error": str(exc), "valid": False}, sort_keys=True))
        return 2
    report = validate_candles(candles)
    print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    return 0 if report.valid else 1

