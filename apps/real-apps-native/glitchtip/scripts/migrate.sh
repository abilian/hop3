#!/bin/bash
set -e

: "${PGHOST:?ERROR: PGHOST is required}"

export DATABASE_URL="${DATABASE_URL:-postgresql://${PGUSER}:${PGPASSWORD}@${PGHOST}:${PGPORT}/${PGDATABASE}}"
export REDIS_URL="${REDIS_URL:-redis://127.0.0.1:6379/0}"
export SECRET_KEY="${SECRET_KEY:-$(head -c 32 /dev/urandom | base64)}"
export GLITCHTIP_DOMAIN="${GLITCHTIP_DOMAIN:-http://localhost:${PORT:-8080}}"

python manage.py migrate --noinput
