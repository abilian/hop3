#!/bin/bash
set -e

# Validate required environment variables (injected by Hop3)
: "${PORT:?ERROR: PORT is required}"
: "${PGHOST:?ERROR: PGHOST is required}"
: "${PGPORT:?ERROR: PGPORT is required}"
: "${PGDATABASE:?ERROR: PGDATABASE is required}"
: "${PGUSER:?ERROR: PGUSER is required}"
: "${PGPASSWORD:?ERROR: PGPASSWORD is required}"

# Set HedgeDoc port from Hop3 PORT
export CMD_PORT="${PORT}"

# Build CMD_DB_URL from PG* variables
export CMD_DB_URL="postgres://${PGUSER}:${PGPASSWORD}@${PGHOST}:${PGPORT}/${PGDATABASE}"

cd /home/hedgedoc/app
exec su hedgedoc -c "cd /home/hedgedoc/app && CMD_PORT=${CMD_PORT} CMD_DB_URL=${CMD_DB_URL} node app.js"
