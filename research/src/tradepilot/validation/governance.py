"""Process-scoped locked-test authorization and conflict prevention."""

from dataclasses import dataclass
from typing import Sequence

from tradepilot.core.canonical import canonical_json_bytes, sha256_hex
from tradepilot.validation.models import (
    LockedTestAuthorization, LockedTestEvaluation, ScenarioEvaluation, SelectionDecision,
)


def verify_authorization(authorization: LockedTestAuthorization) -> None:
    content = {
        "dataset_id": authorization.dataset_id,
        "dataset_checksum": authorization.dataset_checksum,
        "locked_partition_id": authorization.locked_partition_id,
        "strategy_name": authorization.strategy_name,
        "strategy_version": authorization.strategy_version,
        "selected_configuration_fingerprint": authorization.selected_configuration_fingerprint,
        "selection_decision_id": authorization.selection_decision_id,
        "cost_scenario_ids": authorization.cost_scenario_ids,
        "implementation_revision": authorization.implementation_revision,
    }
    if authorization.authorization_id != sha256_hex(canonical_json_bytes(content)):
        raise ValueError("locked-test authorization content does not match its identity")


def authorize_locked_test(
    *, dataset_id: str, dataset_checksum: str, locked_partition_id: str,
    strategy_name: str, strategy_version: str, selection: SelectionDecision,
    cost_scenario_ids: Sequence[str], implementation_revision: str,
) -> LockedTestAuthorization:
    if selection.selected_configuration_fingerprint is None:
        raise ValueError("cannot authorize locked test without a frozen selected configuration")
    content = {
        "dataset_id": dataset_id, "dataset_checksum": dataset_checksum,
        "locked_partition_id": locked_partition_id, "strategy_name": strategy_name,
        "strategy_version": strategy_version,
        "selected_configuration_fingerprint": selection.selected_configuration_fingerprint,
        "selection_decision_id": selection.decision_id,
        "cost_scenario_ids": tuple(cost_scenario_ids),
        "implementation_revision": implementation_revision,
    }
    return LockedTestAuthorization(sha256_hex(canonical_json_bytes(content)), **content)


class LockedTestRegistry:
    """In-memory enforcement only; deterministic IDs do not guarantee human one-time use."""

    def __init__(self) -> None:
        self._results: dict[str, LockedTestEvaluation] = {}

    def publish(
        self, authorization: LockedTestAuthorization,
        scenario_results: Sequence[ScenarioEvaluation],
    ) -> LockedTestEvaluation:
        verify_authorization(authorization)
        if tuple(item.scenario_id for item in scenario_results) != authorization.cost_scenario_ids:
            raise ValueError("locked result cost scenarios do not match authorization")
        result_id = sha256_hex(canonical_json_bytes({
            "authorization_id": authorization.authorization_id,
            "scenario_results": tuple(scenario_results),
        }))
        value = LockedTestEvaluation(authorization.authorization_id, result_id, tuple(scenario_results))
        existing = self._results.get(authorization.authorization_id)
        if existing is not None and existing != value:
            raise ValueError("conflicting locked-test result replacement is forbidden")
        self._results[authorization.authorization_id] = value
        return value

    def get(self, authorization_id: str) -> LockedTestEvaluation | None:
        return self._results.get(authorization_id)
