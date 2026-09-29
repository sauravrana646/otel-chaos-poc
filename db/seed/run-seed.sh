#!/usr/bin/env bash
set -euo pipefail
# Waits for CloudNativePG RW service then applies idempotent seed SQL.
# Intended to run as a Job in otel-poc-apps with network access to poc-postgres-rw.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SQL_FILE="${ROOT}/db/seed/001_schema.sql"

PGHOST="${PGHOST:-poc-postgres-rw}"
PGPORT="${PGPORT:-5432}"
PGUSER="${PGUSER:-poc_app}"
PGDATABASE="${PGDATABASE:-poc}"
export PGPASSWORD="${PGPASSWORD:?PGPASSWORD required}"

echo "Waiting for PostgreSQL at ${PGHOST}:${PGPORT}..."
for i in $(seq 1 60); do
  if pg_isready -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" >/dev/null 2>&1; then
    break
  fi
  sleep 2
  if [[ "$i" -eq 60 ]]; then
    echo "Timed out waiting for database" >&2
    exit 1
  fi
done

psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" -v ON_ERROR_STOP=1 -f "$SQL_FILE"
echo "Seed applied."
