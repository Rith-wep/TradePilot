"""Strict, versioned execution of approved candidate-research workflows."""

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tradepilot.core.canonical import canonical_json_bytes
from tradepilot.data.integrity import verify_dataset
from tradepilot.data.sessions import WeeklySessionCalendar
from tradepilot.reporting.storage import ReportStorage, verify_report
from tradepilot.strategies.breakout import BreakoutConfig
from tradepilot.strategies.pullback import PullbackConfig
from tradepilot.workflows.research_run import build_candidate_research_run, evaluate_candidate_research

CONTRACT_VERSION = "tradepilot-research-execution/v1"
MAX_REQUEST_BYTES = 65_536
SHA256 = re.compile(r"^[0-9a-f]{64}$")
REQUEST_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
INSTRUMENTS = {"EURUSD", "GBPUSD"}
STRATEGIES = {"price_range_breakout": BreakoutConfig, "ema_rsi_trend_pullback": PullbackConfig}


class ExecutionRequestError(ValueError):
    def __init__(self, code: str, message: str, request_id: str = "unknown") -> None:
        super().__init__(message)
        self.code = code
        self.request_id = request_id


def decode(payload: bytes) -> dict[str, Any]:
    if len(payload) > MAX_REQUEST_BYTES:
        raise ExecutionRequestError("REQUEST_TOO_LARGE", "request exceeds its size limit")
    try:
        def strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
            result: dict[str, Any] = {}
            for key, item in pairs:
                if key in result:
                    raise ExecutionRequestError("INVALID_REQUEST", f"duplicate field: {key}")
                result[key] = item
            return result
        value = json.loads(payload.decode("utf-8"), object_pairs_hook=strict_object)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ExecutionRequestError("INVALID_JSON", "request must be valid JSON") from exc
    if not isinstance(value, dict):
        raise ExecutionRequestError("INVALID_REQUEST", "request must be an object")
    return value


def error(request_id: str, code: str, message: str, retryable: bool = False) -> dict[str, object]:
    return {
        "contract_version": CONTRACT_VERSION, "request_id": request_id, "status": "ERROR",
        "error": {"code": code, "message": message, "retryable": retryable},
    }


def _snapshot(root: Path, dataset_id: str, instrument: str) -> Path:
    matches = list(root.glob(f"*/{instrument}/H1/snapshots/{dataset_id}"))
    if len(matches) != 1:
        raise ExecutionRequestError(
            "DATASET_NOT_FOUND" if not matches else "DATASET_LOCATION_CONFLICT",
            "verified dataset snapshot cannot be resolved uniquely",
        )
    resolved = matches[0].resolve(strict=True)
    if not resolved.is_relative_to(root):
        raise ExecutionRequestError("DATASET_PATH_UNSAFE", "dataset escaped the approved root")
    return resolved


def execute(payload: bytes, dataset_root: Path, report_root: Path, source_root: Path) -> tuple[dict[str, object], int]:
    request_id = "unknown"
    try:
        request = decode(payload)
        if set(request) != {
            "contract_version", "request_id", "dataset_id", "instrument", "timeframe",
            "strategy", "implementation_revision",
        }:
            raise ExecutionRequestError("INVALID_REQUEST", "request fields are invalid")
        if isinstance(request.get("request_id"), str) and REQUEST_ID.fullmatch(request["request_id"]):
            request_id = request["request_id"]
        if request.get("contract_version") != CONTRACT_VERSION:
            raise ExecutionRequestError("UNSUPPORTED_CONTRACT", "unsupported contract version", request_id)
        dataset_id = request.get("dataset_id")
        instrument = request.get("instrument")
        strategy = request.get("strategy")
        if not isinstance(dataset_id, str) or not SHA256.fullmatch(dataset_id):
            raise ExecutionRequestError("INVALID_REQUEST", "dataset_id is invalid", request_id)
        if instrument not in INSTRUMENTS or request.get("timeframe") != "H1":
            raise ExecutionRequestError("UNSUPPORTED_MARKET", "instrument or timeframe is unsupported", request_id)
        if strategy not in STRATEGIES:
            raise ExecutionRequestError("UNSUPPORTED_STRATEGY", "strategy is unsupported", request_id)
        expected_revision = request.get("implementation_revision")
        if not isinstance(expected_revision, str) or (
            expected_revision != "unknown"
            and re.fullmatch(r"[0-9a-f]{40}", expected_revision) is None
        ):
            raise ExecutionRequestError("INVALID_REQUEST", "implementation_revision is invalid", request_id)
        snapshot = _snapshot(dataset_root, dataset_id, instrument)
        integrity = verify_dataset(snapshot)
        if not integrity.valid or integrity.dataset_id != dataset_id:
            raise ExecutionRequestError("DATASET_VERIFICATION_FAILED", "dataset integrity verification failed", request_id)
        config = STRATEGIES[strategy]()
        calendar = WeeklySessionCalendar()
        research = evaluate_candidate_research(integrity, calendar, config)
        run = build_candidate_research_run(
            integrity, calendar, research, created_at=datetime.now(timezone.utc),
            implementation_revision=expected_revision,
        )
        stored = ReportStorage(report_root).save(run)
        verified = verify_report(stored.report_path.parent)
        if not verified.valid or verified.report_id != stored.report_id:
            raise ExecutionRequestError("REPORT_VERIFICATION_FAILED", "published report failed verification", request_id)
        return {
            "contract_version": CONTRACT_VERSION, "request_id": request_id, "status": "SUCCEEDED",
            "dataset_id": dataset_id, "report_id": stored.report_id,
            "strategy_name": research.strategy_name, "strategy_version": research.strategy_version,
            "signal_count": len(research.setups), "reused": stored.reused,
        }, 0
    except ExecutionRequestError as exc:
        return error(exc.request_id if exc.request_id != "unknown" else request_id, exc.code, str(exc)), 2
    except OSError:
        return error(request_id, "ARTIFACT_IO_FAILURE", "artifact storage operation failed", True), 3
    except Exception:
        return error(request_id, "RESEARCH_EXECUTION_FAILED", "research execution failed"), 4


def encode(response: dict[str, object]) -> bytes:
    return canonical_json_bytes(response) + b"\n"

