"""Filesystem-persistent sealed partition plans for cross-process governance."""

import json
import os
import uuid
from dataclasses import dataclass
from pathlib import Path

from tradepilot.reporting.canonical import canonical_json_bytes, sha256_hex
from tradepilot.validation.models import ChronologicalPartition, PartitionPolicy


PARTITION_GOVERNANCE_VERSION = "tradepilot-partition-governance/v1"


class PartitionGovernanceError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class SealedPartitionContent:
    schema_version: str
    state: str
    dataset_id: str
    dataset_checksum: str
    policy: PartitionPolicy
    partitions: tuple[ChronologicalPartition, ...]
    locked_test_evaluated: bool


@dataclass(frozen=True, slots=True)
class SealedPartitionPlan:
    plan_id: str
    content: SealedPartitionContent
    path: Path
    reused: bool


def publish_sealed_partitions(
    root: str | Path, *, dataset_id: str, dataset_checksum: str,
    partitions: tuple[ChronologicalPartition, ...], policy: PartitionPolicy | None = None,
) -> SealedPartitionPlan:
    policy = policy or PartitionPolicy()
    if len(partitions) != 3:
        raise PartitionGovernanceError("sealed governance requires training, validation, and locked-test partitions")
    content = SealedPartitionContent(
        PARTITION_GOVERNANCE_VERSION, "SEALED", dataset_id, dataset_checksum,
        policy, partitions, False,
    )
    plan_id = sha256_hex(canonical_json_bytes(content))
    directory = Path(root) / dataset_id
    path = directory / "sealed-partitions.json"
    payload = canonical_json_bytes({"plan_id": plan_id, "content": content})
    if path.exists():
        if path.read_bytes() != payload:
            raise PartitionGovernanceError("existing sealed partition plan is corrupt or conflicting")
        return SealedPartitionPlan(plan_id, content, path, True)
    if directory.exists():
        raise PartitionGovernanceError("incomplete sealed partition directory exists")
    staging = directory.parent / f".staging-{dataset_id}-{uuid.uuid4().hex}"
    staging.mkdir(parents=True)
    (staging / "sealed-partitions.json").write_bytes(payload)
    try:
        os.replace(staging, directory)
    except OSError as exc:
        if path.exists() and path.read_bytes() == payload:
            return SealedPartitionPlan(plan_id, content, path, True)
        raise PartitionGovernanceError("cannot atomically publish sealed partition governance") from exc
    return SealedPartitionPlan(plan_id, content, path, False)


def verify_sealed_partitions(path: str | Path) -> bool:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        content = payload["content"]
        return (
            content.get("state") == "SEALED"
            and content.get("locked_test_evaluated") is False
            and payload.get("plan_id") == sha256_hex(canonical_json_bytes(content))
        )
    except (OSError, KeyError, TypeError, json.JSONDecodeError, ValueError):
        return False
