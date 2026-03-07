#!/bin/bash
set -e

# Validate required environment variables (injected by Hop3)
: "${PORT:?ERROR: PORT is required}"
: "${PGHOST:?ERROR: PGHOST is required}"
: "${PGPORT:?ERROR: PGPORT is required}"
: "${PGDATABASE:?ERROR: PGDATABASE is required}"
: "${PGUSER:?ERROR: PGUSER is required}"
: "${PGPASSWORD:?ERROR: PGPASSWORD is required}"

# Optional with defaults
VIKUNJA_FRONTEND_URL="${VIKUNJA_FRONTEND_URL:-http://localhost:$PORT/}"

# Vikunja uses env vars directly with VIKUNJA_ prefix
export VIKUNJA_SERVICE_INTERFACE=":$PORT"
export VIKUNJA_SERVICE_FRONTENDURL="${VIKUNJA_FRONTEND_URL}"
export VIKUNJA_DATABASE_TYPE="postgres"
export VIKUNJA_DATABASE_HOST="$PGHOST"
export VIKUNJA_DATABASE_PORT="$PGPORT"
export VIKUNJA_DATABASE_DATABASE="$PGDATABASE"
export VIKUNJA_DATABASE_USER="$PGUSER"
export VIKUNJA_DATABASE_PASSWORD="$PGPASSWORD"
export VIKUNJA_FILES_BASEPATH="/app/files"
export VIKUNJA_MAILER_ENABLED="false"
export VIKUNJA_LOG_LEVEL="info"

chown -R vikunja:vikunja /app

# Start Vikunja
exec su vikunja -c "/app/vikunja"
