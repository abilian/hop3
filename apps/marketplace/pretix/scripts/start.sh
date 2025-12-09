#!/bin/bash
# Pretix start script for Hop3

set -eu

DATA_DIR="${HOP3_DATA_DIR:-/app/data}"
CODE_DIR="${HOP3_CODE_DIR:-/app/code}"
PKG_DIR="${HOP3_PKG_DIR:-/app/pkg}"
HOP3_USER="${HOP3_USER:-www-data}"
VENV_PATH="${VENV_PATH:-/app/code/venv}"

echo "=> Starting Pretix"

echo "=> Creating directories"
mkdir -p "${DATA_DIR}/data/media" "${DATA_DIR}/site-packages" /run/pretix

# Activate virtual environment
source ${VENV_PATH}/bin/activate

export PRETIX_CONFIG_FILE=/run/pretix/pretix.cfg

echo "=> Generating nginx.conf"
sed -e "s,##HOSTNAME##,${HOP3_APP_DOMAIN:-localhost}," "${PKG_DIR}/nginx.conf" > /run/nginx.conf

if [[ ! -f "${DATA_DIR}/config.cfg" ]]; then
    cat > "${DATA_DIR}/config.cfg" <<EOF
# Add custom Pretix configuration in this file
# https://docs.pretix.eu/self-hosting/config/#pretix-settings

[pretix]
instance_name=My pretix installation
currency=EUR
EOF

fi

cat "${DATA_DIR}/config.cfg" > /run/pretix/pretix.cfg

crudini --set /run/pretix/pretix.cfg "pretix" "url" "${HOP3_APP_ORIGIN:-http://localhost}"
crudini --set /run/pretix/pretix.cfg "pretix" "trust_x_forwarded_for" "on"
crudini --set /run/pretix/pretix.cfg "pretix" "trust_x_forwarded_proto" "on"

# Database
crudini --set /run/pretix/pretix.cfg "database" "backend" "postgresql"
crudini --set /run/pretix/pretix.cfg "database" "name" "${POSTGRES_DATABASE:-pretix}"
crudini --set /run/pretix/pretix.cfg "database" "user" "${POSTGRES_USERNAME:-pretix}"
crudini --set /run/pretix/pretix.cfg "database" "password" "${POSTGRES_PASSWORD:-}"
crudini --set /run/pretix/pretix.cfg "database" "host" "${POSTGRES_HOST:-localhost}"
crudini --set /run/pretix/pretix.cfg "database" "port" "${POSTGRES_PORT:-5432}"

# SMTP
crudini --set /run/pretix/pretix.cfg "mail" "host" "${SMTP_HOST:-localhost}"
crudini --set /run/pretix/pretix.cfg "mail" "user" "${SMTP_USERNAME:-}"
crudini --set /run/pretix/pretix.cfg "mail" "password" "${SMTP_PASSWORD:-}"
crudini --set /run/pretix/pretix.cfg "mail" "port" "${SMTP_PORT:-25}"
crudini --set /run/pretix/pretix.cfg "mail" "tls" "off"
crudini --set /run/pretix/pretix.cfg "mail" "ssl" "off"
crudini --set /run/pretix/pretix.cfg "mail" "from" "${MAIL_FROM:-noreply@localhost}"
crudini --set /run/pretix/pretix.cfg "mail" "custom_smtp_allow_private_networks" "True"

# Redis
crudini --set /run/pretix/pretix.cfg "redis" "location" "redis://:${REDIS_PASSWORD:-}@${REDIS_HOST:-localhost}/0"

# Celery
crudini --set /run/pretix/pretix.cfg "celery" "backend" "redis://:${REDIS_PASSWORD:-}@${REDIS_HOST:-localhost}/1"
crudini --set /run/pretix/pretix.cfg "celery" "broker" "redis://:${REDIS_PASSWORD:-}@${REDIS_HOST:-localhost}/2"

# OIDC
if [[ -n "${OIDC_ISSUER:-}" ]]; then
    echo "=> Configure OIDC"
    crudini --set /run/pretix/pretix.cfg "pretix" "auth_backends" "pretix.base.auth.NativeAuthBackend,pretix_oidc.auth.OIDCAuthBackend"
    crudini --set /run/pretix/pretix.cfg "oidc" "title" "Login with ${OIDC_PROVIDER_NAME:-SSO}"

    crudini --set /run/pretix/pretix.cfg "oidc" "issuer" "${OIDC_ISSUER}"
    crudini --set /run/pretix/pretix.cfg "oidc" "authorization_endpoint" "${OIDC_AUTH_ENDPOINT:-}"
    crudini --set /run/pretix/pretix.cfg "oidc" "token_endpoint" "${OIDC_TOKEN_ENDPOINT:-}"
    crudini --set /run/pretix/pretix.cfg "oidc" "userinfo_endpoint" "${OIDC_PROFILE_ENDPOINT:-}"
    crudini --set /run/pretix/pretix.cfg "oidc" "end_session_endpoint" ""
    crudini --set /run/pretix/pretix.cfg "oidc" "jwks_uri" "${OIDC_ISSUER}/jwks"

    crudini --set /run/pretix/pretix.cfg "oidc" "client_id" "${OIDC_CLIENT_ID:-}"
    crudini --set /run/pretix/pretix.cfg "oidc" "client_secret" "${OIDC_CLIENT_SECRET:-}"
    crudini --set /run/pretix/pretix.cfg "oidc" "scopes" "openid,email,profile"
    crudini --set /run/pretix/pretix.cfg "oidc" "unique_attribute" "sub"
else
    crudini --set /run/pretix/pretix.cfg "pretix" "auth_backends" "pretix.base.auth.NativeAuthBackend"
fi

# compile static files and translation data and create the database structure
echo "=> Run database migration"
python -m pretix migrate
python -m pretix rebuild

echo "=> Changing permissions"
chown -R ${HOP3_USER}:${HOP3_USER} "${DATA_DIR}" /run/pretix

# run cron script to hide cronjob warning
/app/scripts/cron.sh &

echo "=> Starting Pretix"
exec /usr/bin/supervisord --configuration /etc/supervisor/supervisord.conf --nodaemon -i Pretix
