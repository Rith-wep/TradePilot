"""Reproducible mock historical-ingestion command."""

import argparse
import json
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from typing import Sequence

from tradepilot.data.csv_loader import CandleLoadError, load_candles_csv
from tradepilot.data.ingestion import HistoricalIngestor, IngestionError
from tradepilot.data.models import Instrument
from tradepilot.data.providers.base import ProviderCandle
from tradepilot.data.providers.mock import MockMarketDataProvider
from tradepilot.data.storage import ParquetDatasetStore, StorageError


EURUSD = Instrument("EURUSD", "EUR", "USD", Decimal("0.0001"), 5)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Ingest the synthetic fixture through the mock provider")
    parser.add_argument("--input", type=Path, default=Path("fixtures/synthetic_eurusd_h1.csv"))
    parser.add_argument("--output", type=Path, default=Path("data"))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        fixture = load_candles_csv(args.input, EURUSD)
        if not fixture:
            raise CandleLoadError("fixture contains no candles")
        raw = [ProviderCandle(
            timestamp=candle.timestamp,
            timeframe=candle.timeframe,
            bid_open=str(candle.bid_open), bid_high=str(candle.bid_high),
            bid_low=str(candle.bid_low), bid_close=str(candle.bid_close),
            ask_open=str(candle.ask_open), ask_high=str(candle.ask_high),
            ask_low=str(candle.ask_low), ask_close=str(candle.ask_close),
        ) for candle in fixture]
        provider = MockMarketDataProvider(raw, page_size=2)
        result = HistoricalIngestor(provider, ParquetDatasetStore(args.output)).ingest(
            EURUSD,
            "H1",
            fixture[0].timestamp,
            fixture[-1].timestamp + timedelta(hours=1),
        )
    except (CandleLoadError, IngestionError, StorageError, ValueError) as exc:
        print(json.dumps({"error": str(exc), "success": False}, sort_keys=True))
        return 1
    print(json.dumps({
        "dataset_checksum": result.stored.dataset_checksum,
        "duplicate_count": result.duplicate_count,
        "fetched_count": result.fetched_count,
        "manifest_path": str(result.stored.manifest_path),
        "parquet_path": str(result.stored.parquet_path),
        "quality": result.quality_report.to_dict(),
        "row_count": result.stored.row_count,
        "success": True,
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

