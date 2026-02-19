#!/bin/bash
# Setup Wiki.js configuration from environment variables

set -e

PORT="${PORT:-8080}"
DB_HOST="${PGHOST:-localhost}"
DB_PORT="${PGPORT:-5432}"
DB_NAME="${PGDATABASE:-wikijs}"
DB_USER="${PGUSER:-wikijs}"
DB_PASS="${PGPASSWORD:-}"

cat > config.yml << EOF
port: ${PORT}
bindIP: 0.0.0.0

db:
  type: postgres
  host: ${DB_HOST}
  port: ${DB_PORT}
  user: ${DB_USER}
  pass: ${DB_PASS}
  db: ${DB_NAME}
  ssl: false

logLevel: info

offline: false
ha: false

dataPath: ./data
EOF

mkdir -p data

echo "Wiki.js configuration created"
