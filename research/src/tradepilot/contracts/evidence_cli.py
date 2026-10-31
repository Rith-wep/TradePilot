"""One-request stdin/stdout adapter for candidate evidence projection."""

import argparse
import os
import sys
from pathlib import Path
from typing import Sequence

from tradepilot.contracts.evidence_projection import (
    CONTRACT_VERSION,
    MAX_REQUEST_BYTES,
    approved_report_root,
    process_request,
)
from tradepilot.core.canonical import canonical_json_bytes


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Project verified candidate evidence")
    parser.add_argument(
        "--report-root", type=Path, default=os.environ.get("TRADEPILOT_REPORT_ROOT"),
        required="TRADEPILOT_REPORT_ROOT" not in os.environ,
    )
    args = parser.parse_args(argv)
    payload = sys.stdin.buffer.read(MAX_REQUEST_BYTES + 1)
    try:
        root = approved_report_root(args.report_root)
    except ValueError as exc:
        sys.stderr.write(f"candidate evidence configuration error: {exc}\n")
        response = {
            "contract_version": CONTRACT_VERSION,
            "request_id": "unknown",
            "status": "ERROR",
            "error": {
                "code": "CONFIGURATION_ERROR",
                "message": "approved report root is unavailable",
                "retryable": False,
            },
        }
        sys.stdout.buffer.write(canonical_json_bytes(response) + b"\n")
        return 4
    response, code = process_request(payload, root)
    sys.stdout.buffer.write(canonical_json_bytes(response) + b"\n")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
