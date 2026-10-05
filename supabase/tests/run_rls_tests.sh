#!/usr/bin/env bash
# Run the QueMe Supabase migrations + RLS authorization suite against a
# throwaway local Postgres in Docker. Exits non-zero on any failure.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CONTAINER="${QUEME_PG_TEST_CONTAINER:-queme-pg-test}"
PORT="${QUEME_PG_TEST_PORT:-55432}"
DB="${QUEME_PG_TEST_DB:-queme}"
USER="${QUEME_PG_TEST_USER:-postgres}"

have() { command -v "$1" >/dev/null 2>&1; }

if have docker && docker ps --format '{{.Names}}' 2>/dev/null | grep -qx "$CONTAINER"; then
  echo "Using existing container: $CONTAINER"
else
  if ! have docker; then
    echo "docker is required for migration tests (container $CONTAINER on port $PORT)." >&2
    exit 2
  fi
  docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
  docker run -d --name "$CONTAINER" \
    -e POSTGRES_PASSWORD=test -e POSTGRES_DB="$DB" \
    -p "$PORT:5432" postgres:16-alpine >/dev/null
fi

# Wait for readiness.
for _ in $(seq 1 30); do
  if docker exec "$CONTAINER" pg_isready -U "$USER" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

# Always start from an empty database so the run is repeatable.
docker exec -e PGPASSWORD=test "$CONTAINER" \
  psql -h localhost -U "$USER" -d postgres -q \
  -c "drop database if exists \"$DB\" with (force)" \
  -c "create database \"$DB\""

psql_exec() {
  docker exec -i -e PGPASSWORD=test "$CONTAINER" \
    psql -h localhost -U "$USER" -d "$DB" -v ON_ERROR_STOP=1 -q -f - < "$1"
}

echo "== Applying local auth shim =="
psql_exec "$REPO_ROOT/supabase/tests/00_shim_local_postgres.sql"

echo "== Applying versioned migrations =="
for migration in "$REPO_ROOT"/supabase/migrations/*.sql; do
  echo "-- $(basename "$migration")"
  psql_exec "$migration"
done

echo "== Running RLS authorization suite =="
psql_exec "$REPO_ROOT/supabase/tests/rls_authorization.sql"

echo "PASS: migrations applied and all RLS assertions held."
