"""Strict paired Dukascopy BID/ASK H1 CSV provider."""

import csv
import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path

from tradepilot.data.providers.base import ProviderCandle, ProviderError, ProviderPage, ProviderRequest


EXPECTED_HEADER = ("Etc/UTC", "Open", "High", "Low", "Close", "Volume")
PRICE_NAMES = ("Open", "High", "Low", "Close")


class DukascopyCsvError(ProviderError):
    """The paired source artifacts do not satisfy the import contract."""


@dataclass(frozen=True, slots=True)
class CsvSideRow:
    timestamp: datetime
    open: str
    high: str
    low: str
    close: str
    volume: Decimal
    row_number: int


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    try:
        with Path(path).open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as exc:
        raise DukascopyCsvError(f"cannot read source CSV: {Path(path).name}") from exc
    return digest.hexdigest()


def _expected_hash(name: str, value: str | None, actual: str) -> None:
    if value is None:
        return
    normalized = value.strip().lower()
    if len(normalized) != 64 or any(character not in "0123456789abcdef" for character in normalized):
        raise ValueError(f"expected {name} SHA-256 must be 64 lowercase hexadecimal characters")
    if normalized != actual:
        raise DukascopyCsvError(f"{name} source SHA-256 mismatch")


def _load_side(path: Path, timestamp_format: str, delimiter: str, label: str) -> tuple[CsvSideRow, ...]:
    rows: list[CsvSideRow] = []
    seen: set[datetime] = set()
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle, delimiter=delimiter)
            if tuple(reader.fieldnames or ()) != EXPECTED_HEADER:
                raise DukascopyCsvError(
                    f"{label} CSV header must exactly equal: {', '.join(EXPECTED_HEADER)}"
                )
            previous: datetime | None = None
            for row_number, row in enumerate(reader, start=2):
                try:
                    timestamp = datetime.strptime(row["Etc/UTC"], timestamp_format)
                    if timestamp.tzinfo is None or timestamp.utcoffset() != timedelta(0):
                        raise ValueError("timestamp must explicitly represent UTC")
                    if timestamp.minute or timestamp.second or timestamp.microsecond:
                        raise ValueError("H1 timestamp must be aligned to the hour")
                    if timestamp in seen:
                        raise ValueError("duplicate timestamp")
                    if previous is not None and timestamp < previous:
                        raise ValueError("timestamps must be strictly increasing")
                    values = {name: Decimal(row[name]) for name in PRICE_NAMES}
                    volume = Decimal(row["Volume"])
                    if any(not value.is_finite() for value in (*values.values(), volume)):
                        raise ValueError("prices and volume must be finite")
                    if volume < 0:
                        raise ValueError("volume must not be negative")
                except (KeyError, TypeError, ValueError, InvalidOperation) as exc:
                    raise DukascopyCsvError(f"{label} CSV row {row_number}: {exc}") from exc
                seen.add(timestamp)
                previous = timestamp
                rows.append(CsvSideRow(
                    timestamp, row["Open"], row["High"], row["Low"], row["Close"],
                    volume, row_number,
                ))
    except OSError as exc:
        raise DukascopyCsvError(f"cannot read {label} CSV: {path.name}") from exc
    if not rows:
        raise DukascopyCsvError(f"{label} CSV contains no candles")
    return tuple(rows)


class DukascopyCsvMarketDataProvider:
    """Expose one verified BID/ASK CSV pair through MarketDataProvider."""

    def __init__(
        self,
        bid_path: str | Path,
        ask_path: str | Path,
        *,
        timestamp_format: str,
        delimiter: str = ",",
        expected_bid_sha256: str | None = None,
        expected_ask_sha256: str | None = None,
        is_synthetic: bool = False,
        instrument_symbol: str = "EURUSD",
    ) -> None:
        if not timestamp_format:
            raise ValueError("timestamp_format is required and is never inferred")
        if len(delimiter) != 1:
            raise ValueError("delimiter must be exactly one character")
        if instrument_symbol not in ("EURUSD", "GBPUSD"):
            raise ValueError("Dukascopy CSV instrument must be EURUSD or GBPUSD")
        self.instrument_symbol = instrument_symbol
        self.bid_path = Path(bid_path)
        self.ask_path = Path(ask_path)
        self.timestamp_format = timestamp_format
        self.delimiter = delimiter
        self.bid_sha256 = file_sha256(self.bid_path)
        self.ask_sha256 = file_sha256(self.ask_path)
        _expected_hash("BID", expected_bid_sha256, self.bid_sha256)
        _expected_hash("ASK", expected_ask_sha256, self.ask_sha256)
        bids = _load_side(self.bid_path, timestamp_format, delimiter, "BID")
        asks = _load_side(self.ask_path, timestamp_format, delimiter, "ASK")
        bid_by_time = {item.timestamp: item for item in bids}
        ask_by_time = {item.timestamp: item for item in asks}
        bid_only = sorted(bid_by_time.keys() - ask_by_time.keys())
        ask_only = sorted(ask_by_time.keys() - bid_by_time.keys())
        if bid_only or ask_only:
            detail = (
                f"BID-only={len(bid_only)}, ASK-only={len(ask_only)}; "
                "missing side candles are never fabricated"
            )
            raise DukascopyCsvError(f"BID/ASK timestamps are not aligned: {detail}")
        self._candles = tuple(
            ProviderCandle(
                timestamp=timestamp, timeframe="H1",
                bid_open=bid_by_time[timestamp].open, bid_high=bid_by_time[timestamp].high,
                bid_low=bid_by_time[timestamp].low, bid_close=bid_by_time[timestamp].close,
                ask_open=ask_by_time[timestamp].open, ask_high=ask_by_time[timestamp].high,
                ask_low=ask_by_time[timestamp].low, ask_close=ask_by_time[timestamp].close,
            )
            for timestamp in sorted(bid_by_time)
        )
        pair = hashlib.sha256(f"{self.bid_sha256}:{self.ask_sha256}".encode("ascii")).hexdigest()
        self._dataset_version = f"dukascopy-csv-pair/v1:{pair}"
        self._is_synthetic = is_synthetic
        self.bid_row_count = len(bids)
        self.ask_row_count = len(asks)

    @property
    def name(self) -> str:
        return "dukascopy-csv"

    @property
    def dataset_version(self) -> str:
        return self._dataset_version

    @property
    def is_synthetic(self) -> bool:
        return self._is_synthetic

    @property
    def candles(self) -> tuple[ProviderCandle, ...]:
        return self._candles

    @property
    def start(self) -> datetime:
        return self._candles[0].timestamp

    @property
    def end(self) -> datetime:
        return self._candles[-1].timestamp + timedelta(hours=1)

    def fetch_page(self, request: ProviderRequest, cursor: str | None = None) -> ProviderPage:
        if cursor is not None:
            raise DukascopyCsvError("Dukascopy CSV provider does not use pagination cursors")
        if request.instrument.symbol != self.instrument_symbol or request.timeframe != "H1":
            raise DukascopyCsvError(f"Dukascopy CSV pair represents {self.instrument_symbol} H1")
        values = tuple(item for item in self._candles if request.start <= item.timestamp < request.end)
        metadata = {
            "adapter": "dukascopy-csv/v1",
            "bid_file": self.bid_path.name,
            "ask_file": self.ask_path.name,
            "bid_sha256": self.bid_sha256,
            "ask_sha256": self.ask_sha256,
            "bid_bytes": str(self.bid_path.stat().st_size),
            "ask_bytes": str(self.ask_path.stat().st_size),
            "bid_rows": str(self.bid_row_count),
            "ask_rows": str(self.ask_row_count),
            "timestamp_format": self.timestamp_format,
            "delimiter": self.delimiter,
            "timestamp_convention": "UTC candle open",
            "volume_policy": "validated_not_stored",
        }
        return ProviderPage(values, None, metadata)
