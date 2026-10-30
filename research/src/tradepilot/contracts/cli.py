"""One-request stdin/stdout adapter for trusted artifact verification."""

import argparse
import os
import sys
from pathlib import Path
from typing import Sequence

from tradepilot.contracts.artifact_verification import (
    CONTRACT_VERSION,
    MAX_REQUEST_BYTES,
    ArtifactRoots,
    ContractRequestError,
    REQUEST_ID_PATTERN,
    decode_request,
    process_request,
    request_error_response,
)
from tradepilot.core.canonical import canonical_json_bytes


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify an immutable TradePilot artifact")
    parser.add_argument(
        "--dataset-root", type=Path, default=os.environ.get("TRADEPILOT_DATA_ROOT"),
        required="TRADEPILOT_DATA_ROOT" not in os.environ,
        help="operator-approved dataset storage root",
    )
    parser.add_argument(
        "--report-root", type=Path, default=os.environ.get("TRADEPILOT_REPORT_ROOT"),
        required="TRADEPILOT_REPORT_ROOT" not in os.environ,
        help="operator-approved candidate-report storage root",
    )
    return parser


def _write_response(response: dict[str, object]) -> None:
    sys.stdout.buffer.write(canonical_json_bytes(response) + b"\n")


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = sys.stdin.buffer.read(MAX_REQUEST_BYTES + 1)
    try:
        roots = ArtifactRoots.approved(args.dataset_root, args.report_root)
    except ValueError as exc:
        request_id = "unknown"
        try:
            request = decode_request(payload)
            if (
                isinstance(request.get("request_id"), str)
                and REQUEST_ID_PATTERN.fullmatch(request["request_id"])
            ):
                request_id = request["request_id"]
        except ContractRequestError:
            pass
        sys.stderr.write(f"artifact verifier configuration error: {exc}\n")
        _write_response({
            "contract_version": CONTRACT_VERSION,
            "request_id": request_id,
            "status": "ERROR",
            "error": {
                "code": "CONFIGURATION_ERROR",
                "message": "approved artifact roots are unavailable",
                "retryable": False,
            },
        })
        return 4
    response, exit_code = process_request(payload, roots)
    _write_response(response)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
