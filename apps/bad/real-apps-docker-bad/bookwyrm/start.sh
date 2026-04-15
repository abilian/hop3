#!/bin/bash
set -e

: "${PORT:?ERROR: PORT is required}"
: "${PGHOST:?ERROR: PGHOST is required}"

export POSTGRES_HOST="${PGHOST}"
export POSTGRES_PORT="${PGPORT:-5432}"
export POSTGRES_DB="${PGDATABASE}"
export POSTGRES_USER="${PGUSER}"
export POSTGRES_PASSWORD="${PGPASSWORD}"

export REDIS_ACTIVITY_HOST="${REDIS_HOST:-host.docker.internal}"
export REDIS_ACTIVITY_PORT="${REDIS_PORT:-6379}"
export REDIS_BROKER_HOST="${REDIS_HOST:-host.docker.internal}"
export REDIS_BROKER_PORT="${REDIS_PORT:-6379}"

export SECRET_KEY="${SECRET_KEY:-$(head -c 32 /dev/urandom | base64)}"
export DOMAIN="${DOMAIN:-localhost}"
export DEBUG="false"
export USE_HTTPS="false"
export ALLOWED_HOSTS="*"

# BookWyrm's `environs` strict-load requires the EMAIL_* group even
# when email is unused. Provide stubs; operator overrides for real SMTP.
export EMAIL_HOST="${EMAIL_HOST:-localhost}"
export EMAIL_PORT="${EMAIL_PORT:-25}"
export EMAIL_HOST_USER="${EMAIL_HOST_USER:-noreply}"
export EMAIL_HOST_PASSWORD="${EMAIL_HOST_PASSWORD:-changeme}"
export EMAIL_SENDER_NAME="${EMAIL_SENDER_NAME:-Admin}"
export EMAIL_SENDER_DOMAIN="${EMAIL_SENDER_DOMAIN:-localhost}"
export EMAIL_USE_TLS="false"
export EMAIL_USE_SSL="false"
export DEFAULT_FROM_EMAIL="${DEFAULT_FROM_EMAIL:-noreply@localhost}"

export BOOKWYRM_DATABASE_BACKEND="postgres"

cd /opt/bookwyrm
python manage.py migrate --noinput
python manage.py initdb || true

# Start Celery worker in background (same container; acceptable for
# docker-single-container variant — multi-container is ADR 038 territory).
celery -A celerywyrm worker --loglevel=info --detach --logfile=/tmp/celery.log --pidfile=/tmp/celery.pid || true

exec gunicorn bookwyrm.wsgi:application \
    --bind "0.0.0.0:${PORT}" \
    --pythonpath /opt/bookwyrm \
    --access-logfile - \
    --error-logfile -
