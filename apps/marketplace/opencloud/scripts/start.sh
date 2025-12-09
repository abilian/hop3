#!/bin/bash
# OpenCloud start script for Hop3

set -eu -o pipefail

DATA_DIR="${HOP3_DATA_DIR:-/app/data}"
CODE_DIR="${HOP3_CODE_DIR:-/app/code}"
HOP3_USER="${HOP3_USER:-www-data}"

mkdir -p "${DATA_DIR}/data" "${DATA_DIR}/config"

chown -R ${HOP3_USER}:${HOP3_USER} "${DATA_DIR}"

if [[ ! -f "${DATA_DIR}/config/opencloud.yaml" ]]; then
    echo "==> Init OpenCloud"
    su -s /bin/bash ${HOP3_USER} -c "${CODE_DIR}/opencloud init --insecure true --admin-password changeme"
fi

export OC_DOMAIN="${HOP3_APP_DOMAIN:-localhost}"
export OC_URL="${HOP3_APP_ORIGIN:-http://localhost}"
export OC_INSECURE=true
export PROXY_TLS=false

# Enable notifications service
export OC_ADD_RUN_SERVICES="notifications"

# SMTP configuration
export NOTIFICATIONS_SMTP_HOST="${SMTP_HOST:-localhost}"
export NOTIFICATIONS_SMTP_PORT="${SMTP_STARTTLS_PORT:-587}"
export NOTIFICATIONS_SMTP_SENDER="${MAIL_FROM_DISPLAY_NAME:-OpenCloud} <${MAIL_FROM:-noreply@localhost}>"
export NOTIFICATIONS_SMTP_USERNAME="${SMTP_USERNAME:-}"
export NOTIFICATIONS_SMTP_PASSWORD="${SMTP_PASSWORD:-}"
export NOTIFICATIONS_SMTP_AUTHENTICATION=login
export NOTIFICATIONS_SMTP_ENCRYPTION=starttls
export NOTIFICATIONS_SMTP_INSECURE=false

# OIDC configuration
if [[ -n "${OIDC_ISSUER:-}" ]]; then
    export PROXY_AUTOPROVISION_ACCOUNTS=true
    export OC_OIDC_ISSUER="${OIDC_ISSUER}"
    export IDP_DOMAIN=$(echo "${OIDC_ISSUER}" | awk -F/ '{print $3}')
    export OC_EXCLUDE_RUN_SERVICES=idp,idm  # disable built-in idp
    export WEB_OIDC_CLIENT_ID="${OIDC_CLIENT_ID:-}"
    export PROXY_OIDC_REWRITE_WELLKNOWN=true
    export PROXY_ROLE_ASSIGNMENT_DRIVER=oidc
    export PROXY_USER_OIDC_CLAIM=sub
    export PROXY_OIDC_ACCESS_TOKEN_VERIFY_METHOD=none
fi

echo "==> Starting OpenCloud"
exec su -s /bin/bash ${HOP3_USER} -c "${CODE_DIR}/opencloud server"
