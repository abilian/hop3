#!/bin/bash
# Penpot start script for Hop3

set -eu

DATA_DIR="${HOP3_DATA_DIR:-/app/data}"
HOP3_USER="${HOP3_USER:-www-data}"

mkdir -p /run/penpot "${DATA_DIR}/assets"

export PENPOT_BACKEND_FLAGS="disable-onboarding enable-registration disable-login-with-password disable-email-verification enable-smtp enable-login-with-oidc"
export PENPOT_FRONTEND_FLAGS="disable-onboarding disable-registration disable-login-with-password disable-email-verification enable-smtp enable-login-with-oidc"

[[ ! -f "${DATA_DIR}/.secret_key" ]] && pwgen -1 32 > "${DATA_DIR}/.secret_key"

export NODE_ENV=production

cat > /run/penpot/env.sh <<EOT
## You can read more about all available flags and other
## environment variables for the backend here:
## https://help.penpot.app/technical-guide/configuration/#advanced-configuration
export PENPOT_FLAGS="${PENPOT_BACKEND_FLAGS}"

export PENPOT_PUBLIC_URI=${HOP3_APP_ORIGIN:-http://localhost}
export PENPOT_REDIS_URI="redis://${REDIS_HOST:-localhost}/0"

export PENPOT_SECRET_KEY=$(cat "${DATA_DIR}/.secret_key")

export PENPOT_DATABASE_URI="postgresql://${POSTGRES_HOST:-localhost}/${POSTGRES_DATABASE:-penpot}"
export PENPOT_DATABASE_USERNAME=${POSTGRES_USERNAME:-penpot}
export PENPOT_DATABASE_PASSWORD=${POSTGRES_PASSWORD:-}

export PENPOT_ASSETS_STORAGE_BACKEND=assets-fs
export PENPOT_STORAGE_ASSETS_FS_DIRECTORY=${DATA_DIR}/assets

# OIDC
export PENPOT_OIDC_BASE_URI="${OIDC_ISSUER:-}"
export PENPOT_OIDC_CLIENT_ID="${OIDC_CLIENT_ID:-}"
export PENPOT_OIDC_CLIENT_SECRET="${OIDC_CLIENT_SECRET:-}"
export PENPOT_OIDC_SCOPES="openid profile email"

# SMTP/Email configuration.
export PENPOT_SMTP_DEFAULT_FROM="${MAIL_FROM_DISPLAY_NAME:-Penpot} <${MAIL_FROM:-noreply@localhost}>"
export PENPOT_SMTP_DEFAULT_REPLY_TO="${MAIL_FROM_DISPLAY_NAME:-Penpot} <${MAIL_FROM:-noreply@localhost}>"
export PENPOT_SMTP_HOST=${SMTP_HOST:-localhost}
export PENPOT_SMTP_PORT=${SMTP_PORT:-25}
export PENPOT_SMTP_USERNAME=${SMTP_USERNAME:-}
export PENPOT_SMTP_PASSWORD=${SMTP_PASSWORD:-}
export PENPOT_SMTP_TLS=false
export PENPOT_SMTP_SSL=false

EOT
source /run/penpot/env.sh

cat > /run/config.js <<EOT
var penpotFlags = "${PENPOT_FRONTEND_FLAGS}";
EOT

echo "=> Ensure permissions"
chmod a+x /run/penpot/env.sh
chown -R ${HOP3_USER}:${HOP3_USER} "${DATA_DIR}" /run/penpot

echo "=> Starting supervisor"
exec /usr/bin/supervisord --configuration /etc/supervisor/supervisord.conf --nodaemon -i Penpot
