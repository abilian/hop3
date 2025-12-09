#!/bin/bash
# Baserow start script for Hop3

set -eu

DATA_DIR="${HOP3_DATA_DIR:-/app/data}"
CODE_DIR="${HOP3_CODE_DIR:-/app/code}"
HOP3_USER="${HOP3_USER:-www-data}"

mkdir -p "${DATA_DIR}/media" /run/temp

if [[ ! -f "${DATA_DIR}/.secret" ]]; then
    echo "export SECRET_KEY=$(tr -dc 'a-z0-9' < /dev/urandom | head -c50)" > "${DATA_DIR}/.secret"
fi
source "${DATA_DIR}/.secret"

if [[ ! -f "${DATA_DIR}/env.sh" ]]; then
    echo -e "# Add Baserow customizations here (https://baserow.io/docs/installation/configuration)\n\nexport BASEROW_BACKEND_LOG_LEVEL=INFO\n" > "${DATA_DIR}/env.sh"
fi
source "${DATA_DIR}/env.sh"

export BASEROW_PUBLIC_URL="${HOP3_APP_ORIGIN:-http://localhost}"
export PRIVATE_BACKEND_URL="http://localhost:8000"
export DATABASE_URL="postgresql://${POSTGRES_USERNAME:-baserow}:${POSTGRES_PASSWORD:-}@${POSTGRES_HOST:-localhost}:${POSTGRES_PORT:-5432}/${POSTGRES_DATABASE:-baserow}"
export REDIS_URL="redis://:${REDIS_PASSWORD:-}@${REDIS_HOST:-localhost}"
export MEDIA_ROOT="${DATA_DIR}/media"

export EMAIL_SMTP="true"
export EMAIL_SMTP_USE_TLS=""
export FROM_EMAIL="${MAIL_FROM:-noreply@localhost}"
export EMAIL_SMTP_HOST="${SMTP_HOST:-localhost}"
export EMAIL_SMTP_PORT="${SMTP_PORT:-25}"
export EMAIL_SMTP_USER="${SMTP_USERNAME:-}"
export EMAIL_SMTP_PASSWORD="${SMTP_PASSWORD:-}"

export MIGRATE_ON_STARTUP=false
export BASEROW_TRIGGER_SYNC_TEMPLATES_AFTER_MIGRATION=false

echo "==> Changing ownership"
chown -R ${HOP3_USER}:${HOP3_USER} "${DATA_DIR}"

echo "==> Executing database migrations"
su -s /bin/bash ${HOP3_USER} -c "${CODE_DIR}/env/bin/python ${CODE_DIR}/backend/src/baserow/manage.py migrate"

echo "==> Syncing templates (in the background)"
su -s /bin/bash ${HOP3_USER} -c "${CODE_DIR}/env/bin/python ${CODE_DIR}/backend/src/baserow/manage.py sync_templates" &

echo "==> Starting Baserow"
exec /usr/bin/supervisord --configuration /etc/supervisor/supervisord.conf --nodaemon -i Baserow
