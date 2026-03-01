#!/bin/bash
set -e

# Validate required environment variables (injected by Hop3)
: "${PORT:?ERROR: PORT is required}"
: "${MYSQL_HOST:?ERROR: MYSQL_HOST is required}"
: "${MYSQL_PORT:?ERROR: MYSQL_PORT is required}"
: "${MYSQL_DATABASE:?ERROR: MYSQL_DATABASE is required}"
: "${MYSQL_USER:?ERROR: MYSQL_USER is required}"
: "${MYSQL_PASSWORD:?ERROR: MYSQL_PASSWORD is required}"

cd /home/ghost/app

# Optional with defaults
export GHOST_PORT="${PORT}"
export GHOST_URL="${GHOST_URL:-http://localhost:${GHOST_PORT}}"
export GHOST_LOG_LEVEL="${GHOST_LOG_LEVEL:-info}"
export GHOST_CONTENT_PATH="${GHOST_CONTENT_PATH:-./content}"

# Process config template with envsubst
envsubst < config.production.json.template > config.production.json
chown ghost:ghost config.production.json

# Run Ghost as ghost user
exec su ghost -c "cd /home/ghost/app && node current/index.js"
