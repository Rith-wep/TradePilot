"""Strict loader for the canonical Phase 1 candle CSV format."""

import csv
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from tradepilot.data.models import Candle, Instrument


PRICE_FIELDS = (
    "bid_open", "bid_high", "bid_low", "bid_close",
    "ask_open", "ask_high", "ask_low", "ask_close",
)
REQUIRED_FIELDS = (
    "timestamp", "symbol", "timeframe", *PRICE_FIELDS,
    "source", "dataset_version", "is_synthetic",
)


class CandleLoadError(ValueError):
    """Raised when a candle file cannot satisfy the canonical contract."""


def _parse_boolean(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    raise ValueError("must be true or false")


def load_candles_csv(path: str | Path, instrument: Instrument) -> list[Candle]:
    """Load candles while preserving file order for ordering validation."""

    csv_path = Path(path)
    candles: list[Candle] = []
    try:
        with csv_path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            missing = [field for field in REQUIRED_FIELDS if field not in (reader.fieldnames or [])]
            if missing:
                raise CandleLoadError(f"missing required columns: {', '.join(missing)}")
            for row_number, row in enumerate(reader, start=2):
                try:
                    if row["symbol"] != instrument.symbol:
                        raise ValueError(f"symbol must be {instrument.symbol}")
                    timestamp = datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00"))
                    prices = {field: Decimal(row[field]) for field in PRICE_FIELDS}
                    candles.append(
                        Candle(
                            instrument=instrument,
                            timestamp=timestamp,
                            timeframe=row["timeframe"],
                            **prices,
                            source=row["source"],
                            dataset_version=row["dataset_version"],
                            is_synthetic=_parse_boolean(row["is_synthetic"]),
                        )
                    )
                except (KeyError, TypeError, ValueError, InvalidOperation) as exc:
                    raise CandleLoadError(f"row {row_number}: {exc}") from exc
    except OSError as exc:
        raise CandleLoadError(f"cannot read {csv_path}: {exc}") from exc
    return candles

