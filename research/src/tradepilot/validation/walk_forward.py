"""Expanding walk-forward fold generation with non-overlapping evaluation."""

from typing import Sequence

from tradepilot.data.models import Candle
from tradepilot.core.canonical import canonical_json_bytes, sha256_hex
from tradepilot.validation.models import ChronologicalPartition, PartitionName, WalkForwardFold, WalkForwardPolicy


def expanding_folds(
    candles: Sequence[Candle], training_partition: ChronologicalPartition,
    dataset_id: str, policy: WalkForwardPolicy,
) -> tuple[WalkForwardFold, ...]:
    folds = []
    train_end = training_partition.start_index + policy.initial_training_candles
    fold_index = 0
    while train_end + policy.validation_candles <= training_partition.end_index:
        validation_end = train_end + policy.validation_candles
        train = _partition(candles, dataset_id, PartitionName.TRAINING, training_partition.start_index, train_end, f"fold-{fold_index}-train")
        validation = _partition(candles, dataset_id, PartitionName.VALIDATION, train_end, validation_end, f"fold-{fold_index}-validation")
        fold_id = sha256_hex(canonical_json_bytes({
            "dataset_id": dataset_id, "policy": policy, "index": fold_index,
            "training": train, "validation": validation,
        }))
        folds.append(WalkForwardFold(fold_index, train, validation, fold_id))
        fold_index += 1
        train_end += policy.step_candles
    if not folds:
        raise ValueError("insufficient training coverage for one walk-forward fold")
    for previous, current in zip(folds, folds[1:]):
        if previous.validation.end > current.validation.start:
            raise ValueError("overlapping evaluation windows are not allowed")
    return tuple(folds)


def _partition(candles, dataset_id, name, start_index, end_index, label):
    start = candles[start_index].timestamp
    end = candles[end_index].timestamp
    identity = sha256_hex(canonical_json_bytes({
        "dataset_id": dataset_id, "label": label, "start": start,
        "end": end, "start_index": start_index, "end_index": end_index,
    }))
    return ChronologicalPartition(name, start, end, start_index, end_index, end_index - start_index, identity)
