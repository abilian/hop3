#!/bin/bash
# HedgeDoc start script for Hop3

set -eu

DATA_DIR="${HOP3_DATA_DIR:-/app/data}"
CODE_DIR="${HOP3_CODE_DIR:-/app/code}"
PKG_DIR="${HOP3_PKG_DIR:-/app/pkg}"

mkdir -p "${DATA_DIR}/uploads" /tmp/codimd /run/codimd

if [[ ! -e "${DATA_DIR}/config.json" ]]; then
    echo "==> Creating initial template on first run"
    cp "${PKG_DIR}/templates/config.json.template" "${DATA_DIR}/config.json"
fi

# generate and store an unique sessionSecret for this installation
CONFIG_JSON="${DATA_DIR}/config.json"
if [[ $(jq .production.sessionSecret ${CONFIG_JSON}) == "null" ]]; then
    echo "==> generating sessionSecret"
    sessionsecret=$(openssl rand -hex 32)
    jq ".production.sessionSecret = \"$sessionsecret\"" ${CONFIG_JSON} > /tmp/config.json && mv /tmp/config.json ${CONFIG_JSON}

    if [[ -z "${OIDC_ISSUER:-}" ]]; then
        echo "==> enabling email login"
        jq ".production.allowEmailRegister = true" ${CONFIG_JSON} > /tmp/config.json && mv /tmp/config.json ${CONFIG_JSON}
        jq ".production.email = true" ${CONFIG_JSON} > /tmp/config.json && mv /tmp/config.json ${CONFIG_JSON}
    fi
fi

# these cannot be changed by user (https://docs.hedgedoc.org/configuration/). env vars take precedence over config.json
export CMD_DOMAIN="${HOP3_APP_DOMAIN:-localhost}"
export CMD_PROTOCOL_USESSL="${HOP3_USE_SSL:-true}"
export CMD_DB_URL="${DATABASE_URL:-}"

export CMD_PORT=3000
export CMD_TMP_PATH=/tmp/codimd

if [[ -n "${OIDC_ISSUER:-}" ]]; then
    # https://docs.hedgedoc.org/guides/auth/authelia/
    echo "==> configuring OIDC"
    export CMD_OAUTH2_PROVIDERNAME="${OIDC_PROVIDER_NAME:-SSO}"
    export CMD_OAUTH2_CLIENT_ID="${OIDC_CLIENT_ID}"
    export CMD_OAUTH2_CLIENT_SECRET="${OIDC_CLIENT_SECRET}"
    export CMD_OAUTH2_SCOPE="openid email profile"
    export CMD_OAUTH2_USER_PROFILE_USERNAME_ATTR=sub
    export CMD_OAUTH2_USER_PROFILE_DISPLAY_NAME_ATTR=name
    export CMD_OAUTH2_USER_PROFILE_EMAIL_ATTR=email
    export CMD_OAUTH2_BASE_URL="${OIDC_ISSUER}"
    export CMD_OAUTH2_USER_PROFILE_URL="${OIDC_PROFILE_ENDPOINT}"
    export CMD_OAUTH2_TOKEN_URL="${OIDC_TOKEN_ENDPOINT}"
    export CMD_OAUTH2_AUTHORIZATION_URL="${OIDC_AUTH_ENDPOINT}"
fi

echo "==> Changing permissions"
chown -R "${HOP3_USER:-www-data}:${HOP3_GROUP:-www-data}" "${DATA_DIR}" /tmp/codimd /run/codimd

echo "==> Starting HedgeDoc"
cd "${CODE_DIR}"
exec node app.js
