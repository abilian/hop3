#!/bin/bash
set -e

# Validate required environment variables (injected by Hop3)
: "${PORT:?ERROR: PORT is required}"
: "${PGHOST:?ERROR: PGHOST is required}"
: "${PGPORT:?ERROR: PGPORT is required}"
: "${PGDATABASE:?ERROR: PGDATABASE is required}"
: "${PGUSER:?ERROR: PGUSER is required}"
: "${PGPASSWORD:?ERROR: PGPASSWORD is required}"

# Force correct paths (override Hop3-injected values from host system)
export GITEA_WORK_DIR=/home/gitea
export GITEA_CUSTOM=/home/gitea/custom

# Gitea config (optional with defaults)
export GITEA_APP_NAME="${GITEA_APP_NAME:-Gitea: Git with a cup of tea}"
export GITEA_RUN_MODE="${GITEA_RUN_MODE:-prod}"
export GITEA_REPO_ROOT="${GITEA_REPO_ROOT:-./repos}"
export GITEA_DOMAIN="${GITEA_DOMAIN:-localhost}"
export GITEA_HTTP_PORT="${PORT}"
export GITEA_ROOT_URL="${GITEA_ROOT_URL:-http://localhost:${GITEA_HTTP_PORT}/}"
export GITEA_LOG_LEVEL="${GITEA__log__LEVEL:-Info}"

# Generate secrets if not provided
export GITEA_SECRET_KEY="${GITEA_SECRET_KEY:-$(head -c 32 /dev/urandom | base64)}"
export GITEA_INTERNAL_TOKEN="${GITEA_INTERNAL_TOKEN:-$(head -c 64 /dev/urandom | base64)}"

# Substitute environment variables in config
envsubst < /home/gitea/custom/conf/app.ini.template > /home/gitea/custom/conf/app.ini
chown gitea:gitea /home/gitea/custom/conf/app.ini

# Run Gitea as gitea user
exec su gitea -c "cd /home/gitea && /usr/local/bin/gitea web --config /home/gitea/custom/conf/app.ini"
