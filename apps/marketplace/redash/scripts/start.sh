#!/bin/bash
# Redash start script for Hop3

set -eu -o pipefail

DATA_DIR="${HOP3_DATA_DIR:-/app/data}"
CODE_DIR="${HOP3_CODE_DIR:-/app/code}"
HOP3_USER="${HOP3_USER:-www-data}"

mkdir -p /run/redash /run/snowflake-home

setup_admin() {
    set -eu

    # Wait for app to come up
    while ! curl --fail http://localhost:5000 2>/dev/null; do
        echo "Waiting for redash to come up"
        sleep 1
    done

    curl 'http://localhost:5000/setup' -H 'Content-Type: application/x-www-form-urlencoded' --data 'name=Administrator&email=admin%40localhost&password=changeme&org_name=MyOrg'

    echo "Administrator setup"
}

# migration
[[ -f "${DATA_DIR}/env" ]] && mv "${DATA_DIR}/env" "${DATA_DIR}/env.sh"

# generate initial env file, if it doesn't exist
if [[ ! -f "${DATA_DIR}/env.sh" ]]; then
    echo "==> Generating initial secrets"
    echo "# See env vars at https://redash.io/help/open-source/admin-guide/env-vars-settings/" > "${DATA_DIR}/env.sh"
    echo "export REDASH_COOKIE_SECRET=$(openssl rand -hex 32)" >> "${DATA_DIR}/env.sh"
    echo "export REDASH_SECRET_KEY=$(openssl rand -hex 32)" >> "${DATA_DIR}/env.sh"
    echo "export REDASH_WEB_WORKERS=4" >> "${DATA_DIR}/env.sh"
fi

# https://redash.io/help/open-source/admin-guide/env-vars-settings/
echo "==> Creating environment configs"

# app domain
export REDASH_HOST="${HOP3_APP_ORIGIN:-http://localhost:5000}"

# redis, database, cookie
export REDASH_LOG_LEVEL="INFO"
export REDASH_REDIS_URL="redis://${REDIS_HOST:-localhost}:${REDIS_PORT:-6379}/0"
export REDASH_DATABASE_URL="postgresql://${POSTGRES_USERNAME:-redash}:${POSTGRES_PASSWORD:-}@${POSTGRES_HOST:-localhost}:${POSTGRES_PORT:-5432}/${POSTGRES_DATABASE:-redash}"

# main server config
export REDASH_MAIL_SERVER="${SMTP_HOST:-localhost}"
export REDASH_MAIL_PORT="${SMTP_PORT:-25}"
export REDASH_MAIL_USE_TLS=false
export REDASH_MAIL_USE_SSL=false
export REDASH_MAIL_USERNAME="${SMTP_USERNAME:-}"
export REDASH_MAIL_PASSWORD="${SMTP_PASSWORD:-}"
export REDASH_MAIL_DEFAULT_SENDER="${MAIL_FROM:-noreply@localhost}"

# LDAP
if [[ -n "${LDAP_URL:-}" ]]; then
    export REDASH_LDAP_LOGIN_ENABLED=true
    export REDASH_PASSWORD_LOGIN_ENABLED=true # if made false, there is no way to for ldap user to be admin
    export REDASH_LDAP_URL="${LDAP_URL}"
    export REDASH_LDAP_BIND_DN="${LDAP_BIND_DN:-}"
    export REDASH_LDAP_BIND_DN_PASSWORD="${LDAP_BIND_PASSWORD:-}"
    export REDASH_LDAP_CUSTOM_USERNAME_PROMPT="Username"
    export REDASH_SEARCH_DN="${LDAP_USERS_BASE_DN:-}"
    export REDASH_LDAP_SEARCH_TEMPLATE="(|(mail=%(username)s)(username=%(username)s))"
    export REDASH_LDAP_EMAIL_KEY=mail
    export REDASH_LDAP_DISPLAY_NAME_KEY=displayName
fi

export REDASH_WEB_WORKERS=4
export REDASH_VERSION_CHECK=false

source "${DATA_DIR}/env.sh"

if [[ ! -f "${DATA_DIR}/.setup" ]]; then
    echo "==> First run. Creating tables"
    python "${CODE_DIR}/redash/manage.py" database create_tables
    touch "${DATA_DIR}/.setup"
else
    echo "==> Upgrading redash"
    python "${CODE_DIR}/redash/manage.py" db upgrade
fi

chown -R ${HOP3_USER}:${HOP3_USER} /run/redash "${DATA_DIR}"

if [[ -z "$(python ${CODE_DIR}/redash/manage.py org list 2>/dev/null)" ]]; then
    echo "==> Setting up administrator"
    ( setup_admin ) &
fi

# used in rq. maybe make these configurable via /app/data/env?
export WORKERS_COUNT=4
export HOP3_USER=${HOP3_USER}

echo "==> Starting redash"
exec /usr/bin/supervisord --configuration /etc/supervisor/supervisord.conf --nodaemon -i Redash
