#!/bin/bash
set -e

: "${PORT:?ERROR: PORT is required}"
: "${PGHOST:?ERROR: PGHOST is required}"
: "${PGPORT:?ERROR: PGPORT is required}"
: "${PGDATABASE:?ERROR: PGDATABASE is required}"
: "${PGUSER:?ERROR: PGUSER is required}"
: "${PGPASSWORD:?ERROR: PGPASSWORD is required}"

# Forgejo keeps Gitea's GITEA_* env-var naming for compatibility.
export GITEA_WORK_DIR=/home/forgejo
export GITEA_CUSTOM=/home/forgejo/custom

export GITEA_APP_NAME="${GITEA_APP_NAME:-Forgejo}"
export GITEA_RUN_MODE="${GITEA_RUN_MODE:-prod}"
export GITEA_REPO_ROOT="${GITEA_REPO_ROOT:-./repos}"
export GITEA_DOMAIN="${GITEA_DOMAIN:-localhost}"
export GITEA_HTTP_PORT="${PORT}"
export GITEA_ROOT_URL="${GITEA_ROOT_URL:-http://localhost:${GITEA_HTTP_PORT}/}"
export GITEA_LOG_LEVEL="${GITEA__log__LEVEL:-Info}"

export GITEA_SECRET_KEY="${GITEA_SECRET_KEY:-$(head -c 32 /dev/urandom | base64)}"
export GITEA_INTERNAL_TOKEN="${GITEA_INTERNAL_TOKEN:-$(head -c 64 /dev/urandom | base64)}"

envsubst < /home/forgejo/custom/conf/app.ini.template > /home/forgejo/custom/conf/app.ini
chown forgejo:forgejo /home/forgejo/custom/conf/app.ini

exec su forgejo -c "cd /home/forgejo && /usr/local/bin/forgejo web --config /home/forgejo/custom/conf/app.ini"
