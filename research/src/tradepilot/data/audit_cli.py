"""CLI for integrity and session-aware quality audits of stored datasets."""

import argparse
import json
from datetime import date, time
from pathlib import Path
from typing import Sequence

from tradepilot.data.integrity import verify_dataset
from tradepilot.data.sessions import WeeklySessionCalendar, classify_gaps


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit a TradePilot dataset root or snapshot")
    parser.add_argument("path", type=Path)
    parser.add_argument("--timezone", default="UTC", help="IANA session timezone")
    parser.add_argument("--open-weekday", type=int, default=6, help="Monday=0, Sunday=6")
    parser.add_argument("--open-time", default="22:00")
    parser.add_argument("--close-weekday", type=int, default=4, help="Monday=0, Sunday=6")
    parser.add_argument("--close-time", default="22:00")
    parser.add_argument("--closure-date", action="append", default=[], help="full local closure date, YYYY-MM-DD")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        calendar = WeeklySessionCalendar(
            timezone_name=args.timezone,
            open_weekday=args.open_weekday,
            open_time=time.fromisoformat(args.open_time),
            close_weekday=args.close_weekday,
            close_time=time.fromisoformat(args.close_time),
            closure_dates=frozenset(date.fromisoformat(value) for value in args.closure_date),
            name="audit-calendar",
        )
    except ValueError as exc:
        print(json.dumps({"valid": False, "error": f"invalid calendar configuration: {exc}"}, sort_keys=True))
        return 2
    report = verify_dataset(args.path)
    output = report.to_dict()
    output["gaps"] = classify_gaps(report.candles, calendar).to_dict() if report.candles else None
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0 if report.valid else 1


if __name__ == "__main__":
    raise SystemExit(main())

