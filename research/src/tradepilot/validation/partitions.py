"""Deterministic candle-count partitions with strict half-open UTC boundaries."""

from datetime import timedelta
from decimal import Decimal
from typing import Sequence

from tradepilot.data.models import Candle
from tradepilot.reporting.canonical import canonical_json_bytes, sha256_hex
from tradepilot.validation.models import ChronologicalPartition, PartitionName, PartitionPolicy


def chronological_partitions(
    candles: Sequence[Candle], dataset_id: str, policy: PartitionPolicy | None = None,
) -> tuple[ChronologicalPartition, ChronologicalPartition, ChronologicalPartition]:
    policy = policy or PartitionPolicy()
    values = tuple(candles)
    if len(values) < 5:
        raise ValueError("at least five candles are required for non-empty 60/20/20 partitions")
    if any(current.timestamp <= previous.timestamp for previous, current in zip(values, values[1:])):
        raise ValueError("partition candles must be strictly chronological")
    training_end = int(Decimal(len(values)) * policy.training_fraction)
    validation_end = training_end + int(Decimal(len(values)) * policy.validation_fraction)
    indexes = ((0, training_end), (training_end, validation_end), (validation_end, len(values)))
    names = (PartitionName.TRAINING, PartitionName.VALIDATION, PartitionName.LOCKED_TEST)
    output = []
    for name, (start_index, end_index) in zip(names, indexes, strict=True):
        if end_index <= start_index:
            raise ValueError("dataset coverage is insufficient for requested partitions")
        start = values[start_index].timestamp
        end = values[end_index].timestamp if end_index < len(values) else values[-1].timestamp + timedelta(hours=1)
        identity = sha256_hex(canonical_json_bytes({
            "dataset_id": dataset_id, "policy": policy, "name": name,
            "start": start, "end": end, "start_index": start_index, "end_index": end_index,
        }))
        output.append(ChronologicalPartition(name, start, end, start_index, end_index, end_index - start_index, identity))
    return tuple(output)  # type: ignore[return-value]


def partition_candles(candles: Sequence[Candle], partition: ChronologicalPartition) -> tuple[Candle, ...]:
    values = tuple(candles[partition.start_index:partition.end_index])
    if any(not partition.start <= item.timestamp < partition.end for item in values):
        raise ValueError("partition candle lies outside half-open boundary")
    return values
