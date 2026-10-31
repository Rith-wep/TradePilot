"""One-request stdin/stdout research execution adapter."""

import argparse
import sys
from pathlib import Path
from typing import Sequence

from tradepilot.execution.contract import MAX_REQUEST_BYTES, encode, execute


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--report-root", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    args = parser.parse_args(argv)
    roots = (args.dataset_root.resolve(strict=True), args.report_root.resolve(strict=True))
    response, status = execute(
        sys.stdin.buffer.read(MAX_REQUEST_BYTES + 1), roots[0], roots[1],
        args.source_root.resolve(strict=True),
    )
    sys.stdout.buffer.write(encode(response))
    return status


if __name__ == "__main__":
    raise SystemExit(main())

