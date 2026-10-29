from dataclasses import replace
from datetime import timedelta, timezone

from simulator_helpers import START, candle
from tradepilot.data.integrity import verify_dataset
from tradepilot.data.storage import ParquetDatasetStore


def real_candles(count=240, *, missing=()):
    missing_set = set(missing)
    base = candle(0)
    return tuple(
        replace(
            base,
            timestamp=START + timedelta(hours=index),
            source="oanda-v20", dataset_version="oanda-v20-h1-bid-ask/v1",
            is_synthetic=False,
        )
        for index in range(count) if index not in missing_set
    )


def stored_integrity(root, values):
    store = ParquetDatasetStore(root)
    first = values[0]
    stored = store.save(
        "oanda-v20", first.instrument, "H1", values,
        retrieved_at=START.replace(tzinfo=timezone.utc),
        request_start=values[0].timestamp,
        request_end=values[-1].timestamp + timedelta(hours=1),
    )
    return verify_dataset(stored.snapshot_path), stored
