"""Create one synthetic immutable dataset for Node boundary tests."""

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

research_root = Path(__file__).parents[3] / "research"
sys.path.insert(0, str(research_root / "src"))
sys.path.insert(0, str(research_root / "tests"))

from ingestion_helpers import EURUSD, START, raw_candle  # noqa: E402
from tradepilot.data.normalization import normalize_provider_candle  # noqa: E402
from tradepilot.data.storage import ParquetDatasetStore  # noqa: E402

data_root = Path(sys.argv[1])
candle = normalize_provider_candle(
    raw_candle(0),
    instrument=EURUSD,
    provider="mock",
    dataset_version="node-contract-v1",
    is_synthetic=True,
)
stored = ParquetDatasetStore(data_root).save(
    "mock",
    EURUSD,
    "H1",
    [candle],
    retrieved_at=datetime(2025, 1, 2, tzinfo=timezone.utc),
    request_start=START,
    request_end=START + timedelta(hours=1),
)
print(json.dumps({"dataset_id": stored.dataset_id, "parquet": str(stored.parquet_path)}))
