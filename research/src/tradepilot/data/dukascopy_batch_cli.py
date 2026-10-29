"""CLI for atomic multi-month Dukascopy consolidation and sealed partitions."""

import argparse
import json
from pathlib import Path
from typing import Sequence

from tradepilot.data.dukascopy_batch import DukascopyBatchError, import_batch
from tradepilot.data.storage import ParquetDatasetStore, StorageError
from tradepilot.reporting.canonical import canonical_value
from tradepilot.validation.partition_governance import (
    PartitionGovernanceError, publish_sealed_partitions,
)
from tradepilot.validation.partitions import chronological_partitions


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Import a manifest-driven Dukascopy monthly history")
    parser.add_argument("plan", type=Path)
    parser.add_argument("--output", type=Path, default=Path("data"))
    parser.add_argument("--approve-revisions", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = import_batch(
            args.plan, ParquetDatasetStore(args.output),
            allow_revisions=args.approve_revisions,
        )
        partitions = chronological_partitions(result.integrity.candles, result.stored.dataset_id)
        governance_root = result.stored.snapshot_path.parent.parent / "governance"
        sealed = publish_sealed_partitions(
            governance_root, dataset_id=result.stored.dataset_id,
            dataset_checksum=result.stored.dataset_checksum, partitions=partitions,
        )
    except (DukascopyBatchError, StorageError, PartitionGovernanceError, ValueError) as exc:
        code = "UNAPPROVED_REVISIONS" if "conflicting candle" in str(exc) and not args.approve_revisions else "BATCH_IMPORT_FAILED"
        print(json.dumps({"success": False, "error_code": code, "error": str(exc)}, sort_keys=True))
        return 1
    print(json.dumps({
        "success": True,
        "dataset_id": result.stored.dataset_id,
        "dataset_checksum": result.stored.dataset_checksum,
        "parquet_checksum": result.stored.file_checksum,
        "source_artifacts_checksum": result.artifacts.checksum,
        "row_count": result.stored.row_count,
        "revision_count": len(result.stored.revisions),
        "quality_report_id": result.quality.report_id,
        "monthly_quality": canonical_value(result.quality.monthly),
        "yearly_quality": canonical_value(result.quality.yearly),
        "partition_plan_id": sealed.plan_id,
        "partitions": canonical_value(partitions),
        "locked_test_state": "SEALED",
        "locked_test_evaluated": False,
        "snapshot_path": str(result.stored.snapshot_path),
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
