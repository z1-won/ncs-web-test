#!/bin/sh
set -eu

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  -v app_password="$NCS_DB_PASSWORD" <<'SQL'
CREATE ROLE ncs_app LOGIN PASSWORD :'app_password';
ALTER DATABASE ncs_review OWNER TO ncs_app;
SQL
