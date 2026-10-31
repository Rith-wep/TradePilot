#!/bin/sh
set -eu
if [ "${1:-}" = "-m" ] && [ "${2:-}" = "tradepilot.execution" ]; then
  sleep "${TRADEPILOT_SMOKE_EXECUTION_DELAY_SECONDS:-10}"
fi
exec /usr/local/bin/python "$@"
