#!/bin/sh
set -eu

role="$1"
shift
case "$role" in
  api) role_user="tradepilot_api" ;;
  worker) role_user="tradepilot_worker" ;;
  migrator) role_user="tradepilot_migrator" ;;
  *) echo "unsupported database role" >&2; exit 64 ;;
esac
password="$(cat "/run/secrets/postgres_${role}_password")"
export DATABASE_URL="postgresql://${role_user}:${password}@postgres:5432/tradepilot"
exec "$@"
