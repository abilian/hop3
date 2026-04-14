#!/bin/bash
# Bootstrap Directus: ensure DB env vars are exported in the form Directus
# expects, then run `directus bootstrap` (idempotent — safe to call on each deploy).
set -e

: "${PGHOST:?ERROR: PGHOST is required}"

# Directus reads DB_HOST / DB_PORT / DB_DATABASE / DB_USER / DB_PASSWORD.
export DB_CLIENT="${DB_CLIENT:-pg}"
export DB_HOST="${PGHOST}"
export DB_PORT="${PGPORT:-5432}"
export DB_DATABASE="${PGDATABASE}"
export DB_USER="${PGUSER}"
export DB_PASSWORD="${PGPASSWORD}"

export HOST="${HOST:-0.0.0.0}"
export PORT="${PORT:-8055}"
export PUBLIC_URL="${PUBLIC_URL:-http://localhost:${PORT}}"

# `directus bootstrap` applies migrations and creates the admin user if it
# doesn't exist. Idempotent.
npx directus bootstrap
