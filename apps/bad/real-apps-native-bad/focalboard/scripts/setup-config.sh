#!/bin/bash
set -e
cat > config.json << EOF
{
  "serverRoot": "http://localhost:${PORT:-8080}",
  "port": ${PORT:-8080},
  "dbtype": "postgres",
  "dbconfig": "postgres://${PGUSER:-focalboard}:${PGPASSWORD:-}@${PGHOST:-localhost}:${PGPORT:-5432}/${PGDATABASE:-focalboard}?sslmode=disable",
  "postgres_dbconfig": "postgres://${PGUSER:-focalboard}:${PGPASSWORD:-}@${PGHOST:-localhost}:${PGPORT:-5432}/${PGDATABASE:-focalboard}?sslmode=disable",
  "webpath": "./webapp/pack",
  "filespath": "./files",
  "telemetry": false,
  "session_expire_time": 2592000,
  "session_refresh_time": 18000,
  "localOnly": false,
  "enableLocalMode": true,
  "localModeSocketLocation": "/var/tmp/focalboard_local.socket"
}
EOF
mkdir -p files
echo "Focalboard configuration created"
