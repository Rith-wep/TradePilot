#!/bin/sh
set -eu

api_password="$(cat /run/secrets/postgres_api_password)"
worker_password="$(cat /run/secrets/postgres_worker_password)"
migrator_password="$(cat /run/secrets/postgres_migrator_password)"

psql --set=ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  --set=api_password="$api_password" \
  --set=worker_password="$worker_password" \
  --set=migrator_password="$migrator_password" <<'SQL'
SELECT format('CREATE ROLE tradepilot_migrator LOGIN PASSWORD %L', :'migrator_password')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'tradepilot_migrator') \gexec
SELECT format('CREATE ROLE tradepilot_api LOGIN PASSWORD %L', :'api_password')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'tradepilot_api') \gexec
SELECT format('CREATE ROLE tradepilot_worker LOGIN PASSWORD %L', :'worker_password')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'tradepilot_worker') \gexec

ALTER DATABASE tradepilot OWNER TO tradepilot_migrator;
REVOKE ALL ON DATABASE tradepilot FROM PUBLIC;
GRANT CONNECT ON DATABASE tradepilot TO tradepilot_api, tradepilot_worker;
SQL
