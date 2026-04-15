#!/bin/bash
set -e

: "${PORT:?ERROR: PORT is required}"
: "${PGHOST:?ERROR: PGHOST is required}"

export DATABASE_URL="${DATABASE_URL:-postgresql://${PGUSER}:${PGPASSWORD}@${PGHOST}:${PGPORT}/${PGDATABASE}}"
export REDIS_URL="${REDIS_URL:-redis://host.docker.internal:6379/0}"
export SECRET_KEY="${SECRET_KEY:-$(head -c 32 /dev/urandom | base64)}"
export GLITCHTIP_DOMAIN="${GLITCHTIP_DOMAIN:-http://localhost:${PORT}}"

cd /opt/glitchtip
python manage.py migrate --noinput

exec granian glitchtip.wsgi:application \
    --interface wsgi \
    --host 0.0.0.0 \
    --port "${PORT}"
