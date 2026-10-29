"""Full-prefix warm-up with strict evaluation-signal and boundary isolation."""

from typing import Sequence

from tradepilot.data.models import Candle
from tradepilot.strategies.models import SetupRecord
from tradepilot.validation.models import ChronologicalPartition


def historical_prefix(candles: Sequence[Candle], partition: ChronologicalPartition) -> tuple[Candle, ...]:
    """Return all history through the partition end for recursive smoothing."""
    return tuple(candles[:partition.end_index])


def eligible_setups(setups: Sequence[SetupRecord], partition: ChronologicalPartition) -> tuple[SetupRecord, ...]:
    eligible = []
    for setup in setups:
        detection_inside = partition.start <= setup.detection_candle_open_time < partition.end
        observable_inside = partition.start <= setup.observable_at < partition.end
        if detection_inside and observable_inside:
            eligible.append(setup)
    return tuple(sorted(eligible, key=lambda item: (item.observable_at, item.identity_key)))
