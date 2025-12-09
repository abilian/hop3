#!/bin/bash
# Weblate start script for Hop3

set -eu -o pipefail

DATA_DIR="${HOP3_DATA_DIR:-/app/data}"
CODE_DIR="${HOP3_CODE_DIR:-/app/code}"
HOP3_USER="${HOP3_USER:-www-data}"

cd "${CODE_DIR}"

echo "=> Ensure directories"
mkdir -p /run/weblate /run/nginx /run/gunicorn/app/weblate

source "${CODE_DIR}/venv/bin/activate"

echo "=> Generating nginx.conf"
sed -e "s,##HOSTNAME##,${HOP3_APP_DOMAIN:-localhost}," "${CODE_DIR}/weblate.nginx" > /run/nginx.conf

echo "=> Get secret key"
if [[ ! -f "${DATA_DIR}/.secret_key" ]]; then
    weblate-generate-secret-key > "${DATA_DIR}/.secret_key"
fi
export SECRET_KEY=$(<"${DATA_DIR}/.secret_key")

[[ -z "${OIDC_PROVIDER_NAME:-}" ]] && export OIDC_PROVIDER_NAME="SSO"

echo "=> Ensure custom_settings"
if [[ ! -f "${DATA_DIR}/custom_settings.py" ]]; then
    echo -e '# Add custom settings here to override the defaults\n# https://docs.weblate.org/en/latest/admin/config.html\n\n' > "${DATA_DIR}/custom_settings.py"
fi

# Database configuration
export WEBLATE_DATABASE_HOST="${POSTGRES_HOST:-localhost}"
export WEBLATE_DATABASE_PORT="${POSTGRES_PORT:-5432}"
export WEBLATE_DATABASE_NAME="${POSTGRES_DATABASE:-weblate}"
export WEBLATE_DATABASE_USER="${POSTGRES_USERNAME:-weblate}"
export WEBLATE_DATABASE_PASSWORD="${POSTGRES_PASSWORD:-}"

# Redis configuration
export WEBLATE_REDIS_HOST="${REDIS_HOST:-localhost}"
export WEBLATE_REDIS_PORT="${REDIS_PORT:-6379}"
export WEBLATE_REDIS_PASSWORD="${REDIS_PASSWORD:-}"

# Email configuration
export WEBLATE_EMAIL_HOST="${SMTP_HOST:-localhost}"
export WEBLATE_EMAIL_PORT="${SMTP_PORT:-25}"
export WEBLATE_EMAIL_HOST_USER="${SMTP_USERNAME:-}"
export WEBLATE_EMAIL_HOST_PASSWORD="${SMTP_PASSWORD:-}"
export WEBLATE_DEFAULT_FROM_EMAIL="${MAIL_FROM:-noreply@localhost}"

# Site URL
export WEBLATE_SITE_DOMAIN="${HOP3_APP_DOMAIN:-localhost}"
export WEBLATE_ENABLE_HTTPS=true

echo "=> Run migration"
weblate migrate

if [[ ! -f "${DATA_DIR}/.admin_created" ]]; then
    echo "=> Ensure admin"
    weblate createadmin --password "changeme123" --username "admin" --email "admin@cloudron.local"
    touch "${DATA_DIR}/.admin_created"
fi

echo "=> Ensure permissions"
chown -R ${HOP3_USER}:${HOP3_USER} "${DATA_DIR}" /run/weblate /run/gunicorn

echo "=> Build assets"
su -s /bin/bash ${HOP3_USER} -c "weblate collectstatic --noinput --clear --link"
su -s /bin/bash ${HOP3_USER} -c "weblate compress"

echo "=> Ensure and source celery config overrides"
# make sure options for the celery workers exist
export CELERY_MAIN_OPTIONS=""
export CELERY_NOTIFY_OPTIONS=""
export CELERY_TRANSLATE_OPTIONS=""
export CELERY_BACKUP_OPTIONS=""
export CELERY_BEAT_OPTIONS=""
export CELERY_MEMORY_OPTIONS=""

# source custom overrides
if [[ ! -f "${DATA_DIR}/celery.env" ]]; then
    echo -e 'export CELERY_MAIN_OPTIONS=""\nexport CELERY_NOTIFY_OPTIONS=""\nexport CELERY_TRANSLATE_OPTIONS=""\nexport CELERY_BACKUP_OPTIONS=""\nexport CELERY_BEAT_OPTIONS=""\nexport CELERY_MEMORY_OPTIONS=""\n' > "${DATA_DIR}/celery.env"
fi
source "${DATA_DIR}/celery.env"

# Required celery env vars
export CELERY_WORKER_RUNNING=1
export CELERY_BROKER_URL="redis://:${REDIS_PASSWORD:-}@${REDIS_HOST:-localhost}"
export CELERY_RESULT_BACKEND="${CELERY_BROKER_URL}"

echo "=> Starting supervisor"
exec /usr/bin/supervisord --configuration /etc/supervisor/supervisord.conf --nodaemon -i weblate
