import unittest
from dataclasses import replace

from validation_helpers import evaluation, scenario
from tradepilot.validation.governance import LockedTestRegistry, authorize_locked_test
from tradepilot.validation.parameters import select_configuration


class LockedTestGovernanceTests(unittest.TestCase):
    def _authorization(self):
        selection = select_configuration((evaluation(),), minimum_trades=1)
        return authorize_locked_test(
            dataset_id="a" * 64, dataset_checksum="b" * 64,
            locked_partition_id="c" * 64, strategy_name="strategy",
            strategy_version="1.0.0", selection=selection,
            cost_scenario_ids=("d" * 64,), implementation_revision="revision",
        )

    def test_authorization_requires_frozen_selection(self) -> None:
        empty = select_configuration((), minimum_trades=1)
        with self.assertRaisesRegex(ValueError, "frozen"):
            authorize_locked_test(
                dataset_id="a" * 64, dataset_checksum="b" * 64,
                locked_partition_id="c" * 64, strategy_name="strategy",
                strategy_version="1", selection=empty, cost_scenario_ids=(),
                implementation_revision="revision",
            )

    def test_identical_result_retrieval_and_conflict_rejection(self) -> None:
        authorization = self._authorization()
        value = replace(scenario(), scenario_id="d" * 64)
        registry = LockedTestRegistry()
        first = registry.publish(authorization, (value,))
        self.assertEqual(registry.publish(authorization, (value,)), first)
        conflict = replace(value, accounting_report_id="e" * 64)
        with self.assertRaisesRegex(ValueError, "conflicting"):
            registry.publish(authorization, (conflict,))

    def test_locked_evaluation_cannot_enter_selection(self) -> None:
        authorization = self._authorization()
        value = replace(scenario(), scenario_id="d" * 64)
        locked = LockedTestRegistry().publish(authorization, (value,))
        with self.assertRaisesRegex(ValueError, "locked-test"):
            select_configuration((locked,), minimum_trades=1)  # type: ignore[arg-type]

    def test_tampered_authorization_is_rejected(self) -> None:
        authorization = replace(self._authorization(), dataset_id="f" * 64)
        value = replace(scenario(), scenario_id="d" * 64)
        with self.assertRaisesRegex(ValueError, "identity"):
            LockedTestRegistry().publish(authorization, (value,))


if __name__ == "__main__": unittest.main()
