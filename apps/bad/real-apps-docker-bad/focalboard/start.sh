#!/bin/bash
set -e

# Validate required environment variables (injected by Hop3)
: "${PORT:?ERROR: PORT is required}"
: "${DATABASE_URL:?ERROR: DATABASE_URL is required}"

cd /opt/focalboard

# Create config from environment
cat > config.json << EOF
{
  "serverRoot": "http://localhost:${PORT}",
  "port": ${PORT},
  "dbtype": "postgres",
  "dbconfig": "${DATABASE_URL}",
  "useSSL": false,
  "webpath": "./pack",
  "filespath": "./files",
  "telemetry": false,
  "session_expire_time": 2592000,
  "session_refresh_time": 18000,
  "localOnly": false,
  "enableLocalMode": true,
  "localModeSocketLocation": "/var/tmp/focalboard_local.socket"
}
EOF

exec ./bin/focalboard-server
