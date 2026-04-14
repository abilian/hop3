#!/bin/bash
set -e

: "${PORT:?ERROR: PORT is required}"
: "${PGHOST:?ERROR: PGHOST is required}"

cd /opt/directus

export DB_CLIENT="${DB_CLIENT:-pg}"
export DB_HOST="${PGHOST}"
export DB_PORT="${PGPORT:-5432}"
export DB_DATABASE="${PGDATABASE}"
export DB_USER="${PGUSER}"
export DB_PASSWORD="${PGPASSWORD}"

export HOST="0.0.0.0"
export PUBLIC_URL="${PUBLIC_URL:-http://localhost:${PORT}}"
export KEY="${KEY:-$(head -c 32 /dev/urandom | base64)}"
export SECRET="${SECRET:-$(head -c 32 /dev/urandom | base64)}"
export ADMIN_EMAIL="${ADMIN_EMAIL:-admin@example.com}"
export ADMIN_PASSWORD="${ADMIN_PASSWORD:-$(head -c 16 /dev/urandom | base64)}"

npx directus bootstrap
exec npx directus start
