#!/bin/sh
set -e

echo "==> Starting HedgeDoc"

# Create directories
mkdir -p /app/uploads /app/tmp

# Generate session secret if not set
if [ -z "$CMD_SESSION_SECRET" ]; then
    export CMD_SESSION_SECRET=$(cat /dev/urandom | tr -dc 'a-zA-Z0-9' | fold -w 32 | head -n 1)
    echo "Generated CMD_SESSION_SECRET"
fi

# Use DATABASE_URL if CMD_DB_URL not set
if [ -z "$CMD_DB_URL" ] && [ -n "$DATABASE_URL" ]; then
    export CMD_DB_URL="$DATABASE_URL"
    echo "Set CMD_DB_URL from DATABASE_URL"
fi

# Set domain from HOST_NAME if available
if [ -z "$CMD_DOMAIN" ] && [ -n "$HOST_NAME" ]; then
    export CMD_DOMAIN="$HOST_NAME"
    echo "Set CMD_DOMAIN from HOST_NAME: $CMD_DOMAIN"
fi

# Set PORT for internal use
INTERNAL_PORT=${PORT:-3000}

# Debug: show key env vars
echo "CMD_DB_URL: ${CMD_DB_URL:-NOT SET}"
echo "CMD_DOMAIN: ${CMD_DOMAIN:-NOT SET}"
echo "INTERNAL_PORT: ${INTERNAL_PORT}"

# Create config.json for HedgeDoc (required in production mode)
# Environment variables will override these values
cat > /app/config.json << EOF
{
  "production": {
    "db": {
      "dialect": "postgres",
      "url": "${CMD_DB_URL}"
    },
    "port": ${INTERNAL_PORT},
    "domain": "${CMD_DOMAIN:-localhost}",
    "protocolUseSSL": true,
    "allowAnonymous": true,
    "allowAnonymousEdits": true,
    "allowFreeURL": true,
    "defaultPermission": "freely",
    "sessionSecret": "${CMD_SESSION_SECRET}",
    "uploadsPath": "/app/uploads"
  }
}
EOF

echo "==> Created config.json"
cat /app/config.json

# Start HedgeDoc
echo "==> Starting Node.js server"
exec node app.js
