import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from validation_helpers import candles
from tradepilot.validation.partition_governance import (
    PartitionGovernanceError, publish_sealed_partitions, verify_sealed_partitions,
)
from tradepilot.validation.partitions import chronological_partitions


class PartitionGovernanceTests(unittest.TestCase):
    def test_sealed_plan_is_reusable_and_never_marks_test_evaluated(self):
        with tempfile.TemporaryDirectory() as root:
            parts = chronological_partitions(candles(100), "a" * 64)
            first = publish_sealed_partitions(
                root, dataset_id="a" * 64, dataset_checksum="b" * 64, partitions=parts,
            )
            second = publish_sealed_partitions(
                root, dataset_id="a" * 64, dataset_checksum="b" * 64, partitions=parts,
            )
            self.assertEqual(first.plan_id, second.plan_id)
            self.assertTrue(second.reused)
            self.assertFalse(first.content.locked_test_evaluated)
            self.assertTrue(verify_sealed_partitions(first.path))

    def test_dataset_identity_changes_partitions_and_corruption_fails_closed(self):
        with tempfile.TemporaryDirectory() as root:
            first_parts = chronological_partitions(candles(100), "a" * 64)
            second_parts = chronological_partitions(candles(100), "c" * 64)
            self.assertNotEqual(first_parts[-1].partition_id, second_parts[-1].partition_id)
            plan = publish_sealed_partitions(
                root, dataset_id="a" * 64, dataset_checksum="b" * 64, partitions=first_parts,
            )
            plan.path.write_text("{}", encoding="utf-8")
            self.assertFalse(verify_sealed_partitions(plan.path))
            with self.assertRaisesRegex(PartitionGovernanceError, "corrupt"):
                publish_sealed_partitions(
                    root, dataset_id="a" * 64, dataset_checksum="b" * 64, partitions=first_parts,
                )


if __name__ == "__main__": unittest.main()
