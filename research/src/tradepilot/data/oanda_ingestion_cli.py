"""Credential-safe OANDA v20 historical ingestion command."""

import argparse
import json
import os
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Sequence

from tradepilot.data.ingestion import HistoricalIngestor, IngestionConfig, IngestionError
from tradepilot.data.models import Instrument
from tradepilot.data.providers.oanda import OandaMarketDataProvider, OandaProviderConfig
from tradepilot.data.storage import ParquetDatasetStore, StorageError


INSTRUMENTS = {
    "EURUSD": Instrument("EURUSD", "EUR", "USD", Decimal("0.0001"), 5),
    "GBPUSD": Instrument("GBPUSD", "GBP", "USD", Decimal("0.0001"), 5),
}


def _utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.utcoffset() != timedelta(0):
        raise argparse.ArgumentTypeError("timestamp must be UTC, for example 2024-01-01T00:00:00Z")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Ingest OANDA v20 H1 bid/ask candles")
    parser.add_argument("instrument", choices=tuple(INSTRUMENTS))
    parser.add_argument("--start", required=True, type=_utc)
    parser.add_argument("--end", required=True, type=_utc)
    parser.add_argument("--environment", choices=("practice", "live"), default="practice")
    parser.add_argument("--output", type=Path, default=Path("data"))
    parser.add_argument("--requests-per-second", type=float, default=2.0)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--max-retries", type=int, default=3)
    parser.add_argument("--batch-days", type=int, default=90)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    token = os.environ.get("OANDA_API_TOKEN", "")
    account_id = os.environ.get("OANDA_ACCOUNT_ID", "")
    if not token or not account_id:
        print(json.dumps({"success": False, "error": "OANDA credentials are not configured"}))
        return 2
    try:
        provider = OandaMarketDataProvider(
            token, account_id,
            config=OandaProviderConfig(
                environment=args.environment,
                requests_per_second=args.requests_per_second,
            ),
        )
        ingestor = HistoricalIngestor(
            provider,
            ParquetDatasetStore(args.output),
            config=IngestionConfig(
                batch_duration=timedelta(days=args.batch_days),
                request_timeout_seconds=args.timeout,
                max_retries=args.max_retries,
            ),
        )
        result = ingestor.ingest(INSTRUMENTS[args.instrument], "H1", args.start, args.end)
    except (IngestionError, StorageError, ValueError) as exc:
        # Adapter exceptions deliberately contain no token, account ID, URL, or response body.
        print(json.dumps({"success": False, "error": str(exc)}, sort_keys=True))
        return 1
    print(json.dumps({
        "success": True,
        "dataset_id": result.stored.dataset_id,
        "dataset_checksum": result.stored.dataset_checksum,
        "row_count": result.stored.row_count,
        "duplicate_count": result.duplicate_count,
        "retry_count": result.retry_count,
        "quality": result.quality_report.to_dict(),
        "snapshot_path": str(result.stored.snapshot_path),
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
