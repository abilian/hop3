#!/bin/bash
set -e

: "${PGHOST:?ERROR: PGHOST is required}"

# BookWyrm reads a long list of env vars directly; map our addons to
# the ones that matter for deploy and health-check.
export POSTGRES_HOST="${PGHOST}"
export POSTGRES_PORT="${PGPORT:-5432}"
export POSTGRES_DB="${PGDATABASE}"
export POSTGRES_USER="${PGUSER}"
export POSTGRES_PASSWORD="${PGPASSWORD}"

export REDIS_ACTIVITY_HOST="127.0.0.1"
export REDIS_ACTIVITY_PORT="6379"
export REDIS_BROKER_HOST="127.0.0.1"
export REDIS_BROKER_PORT="6379"

export SECRET_KEY="${SECRET_KEY:-$(head -c 32 /dev/urandom | base64)}"
export DOMAIN="${DOMAIN:-localhost}"
export DEBUG="false"
export USE_HTTPS="false"
export ALLOWED_HOSTS="*"

# BookWyrm's `environs` strict-load requires the EMAIL_* group even
# when email is unused. Provide stub values; the operator overrides
# at runtime when wiring real SMTP.
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

python manage.py migrate --noinput
python manage.py initdb || true
