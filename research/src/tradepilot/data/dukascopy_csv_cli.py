"""Import a verified Dukascopy EURUSD H1 BID/ASK CSV pair."""

import argparse
import json
from datetime import time
from decimal import Decimal
from math import ceil
from pathlib import Path
from statistics import median
from typing import Sequence

from tradepilot.data.ingestion import HistoricalIngestor, IngestionError
from tradepilot.data.integrity import verify_dataset
from tradepilot.data.models import Instrument
from tradepilot.data.providers.dukascopy_csv import DukascopyCsvError, DukascopyCsvMarketDataProvider
from tradepilot.data.sessions import WeeklySessionCalendar, classify_gaps
from tradepilot.data.storage import ParquetDatasetStore, StorageError


EURUSD = Instrument("EURUSD", "EUR", "USD", Decimal("0.0001"), 5)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Import paired Dukascopy H1 BID/ASK CSV files")
    parser.add_argument("--instrument", choices=("EURUSD",), required=True)
    parser.add_argument("--bid", type=Path, required=True)
    parser.add_argument("--ask", type=Path, required=True)
    parser.add_argument("--timestamp-format", required=True, help="explicit Python strptime format")
    parser.add_argument("--delimiter", default=",")
    parser.add_argument("--expected-bid-sha256", default=None)
    parser.add_argument("--expected-ask-sha256", default=None)
    parser.add_argument("--output", type=Path, default=Path("data"))
    parser.add_argument("--strict-gaps", action="store_true")
    parser.add_argument("--approve-revisions", action="store_true")
    return parser


def _calendar() -> WeeklySessionCalendar:
    return WeeklySessionCalendar(
        "America/New_York", 6, time(17), 4, time(17), frozenset(), "dukascopy-fx-week",
    )


def _coverage(provider, calendar) -> dict[str, object]:
    observed = {item.timestamp for item in provider.candles}
    expected = set()
    current = provider.start
    while current < provider.end:
        if calendar.is_expected_open(current):
            expected.add(current)
        from datetime import timedelta
        current += timedelta(hours=1)
    matched = observed & expected
    return {
        "range_start": provider.start,
        "range_end": provider.end,
        "row_count": len(observed),
        "expected_open_candles": len(expected),
        "observed_expected_candles": len(matched),
        "coverage_ratio": Decimal(len(matched)) / Decimal(len(expected)) if expected else Decimal(0),
    }


def _spreads(candles) -> dict[str, object]:
    values = sorted(
        (ask - bid) / candle.instrument.pip_size
        for candle in candles
        for bid, ask in zip(
            (candle.bid_open, candle.bid_high, candle.bid_low, candle.bid_close),
            (candle.ask_open, candle.ask_high, candle.ask_low, candle.ask_close),
        )
    )
    return {
        "observation_count": len(values),
        "minimum_pips": values[0] if values else None,
        "median_pips": median(values) if values else None,
        "percentile_95_pips": values[max(0, ceil(Decimal("0.95") * len(values)) - 1)] if values else None,
        "maximum_pips": values[-1] if values else None,
        "unusual_over_20_pips": sum(item > Decimal(20) for item in values),
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        provider = DukascopyCsvMarketDataProvider(
            args.bid, args.ask, timestamp_format=args.timestamp_format,
            delimiter=args.delimiter,
            expected_bid_sha256=args.expected_bid_sha256,
            expected_ask_sha256=args.expected_ask_sha256,
        )
        calendar = _calendar()
        gaps = classify_gaps(provider.candles, calendar)  # only timestamp is consumed
        coverage = _coverage(provider, calendar)
        if args.strict_gaps and gaps.unexpected_missing_count:
            print(json.dumps({
                "success": False, "error_code": "UNEXPECTED_GAPS",
                "coverage": coverage, "gaps": gaps.to_dict(),
                "bid_sha256": provider.bid_sha256, "ask_sha256": provider.ask_sha256,
            }, default=str, indent=2, sort_keys=True))
            return 1
        result = HistoricalIngestor(provider, ParquetDatasetStore(args.output)).ingest(
            EURUSD, "H1", provider.start, provider.end,
            allow_revisions=args.approve_revisions,
        )
        integrity = verify_dataset(result.stored.snapshot_path)
        if not integrity.valid:
            raise StorageError("stored Dukascopy snapshot failed integrity verification")
    except (DukascopyCsvError, IngestionError, StorageError, ValueError) as exc:
        code = "UNAPPROVED_REVISIONS" if "conflicting candle" in str(exc) and not args.approve_revisions else "IMPORT_FAILED"
        print(json.dumps({"success": False, "error_code": code, "error": str(exc)}, sort_keys=True))
        return 1
    print(json.dumps({
        "success": True,
        "provider": provider.name,
        "instrument": "EURUSD",
        "timeframe": "H1",
        "dataset_id": integrity.dataset_id,
        "dataset_checksum": integrity.dataset_checksum,
        "parquet_checksum": integrity.parquet_checksum,
        "bid_sha256": provider.bid_sha256,
        "ask_sha256": provider.ask_sha256,
        "dataset_version": provider.dataset_version,
        "coverage": coverage,
        "gaps": gaps.to_dict(),
        "spreads": _spreads(integrity.candles),
        "quality": integrity.quality_report.to_dict() if integrity.quality_report else None,
        "duplicate_count": result.duplicate_count,
        "revision_count": len(result.stored.revisions),
        "revisions_approved": args.approve_revisions,
        "snapshot_path": str(result.stored.snapshot_path),
        "manifest_path": str(result.stored.manifest_path),
    }, default=str, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
