#!/bin/bash
# Setup Ghost configuration from environment variables

set -e

PORT="${PORT:-8080}"
DB_HOST="${MYSQL_HOST:-localhost}"
DB_PORT="${MYSQL_PORT:-3306}"
DB_NAME="${MYSQL_DATABASE:-ghost}"
DB_USER="${MYSQL_USER:-ghost}"
DB_PASS="${MYSQL_PASSWORD:-}"
SITE_URL="${SITE_URL:-http://localhost:${PORT}}"

cat > config.production.json << EOF
{
  "url": "${SITE_URL}",
  "server": {
    "port": ${PORT},
    "host": "0.0.0.0"
  },
  "database": {
    "client": "mysql",
    "connection": {
      "host": "${DB_HOST}",
      "port": ${DB_PORT},
      "user": "${DB_USER}",
      "password": "${DB_PASS}",
      "database": "${DB_NAME}"
    }
  },
  "mail": {
    "transport": "Direct"
  },
  "logging": {
    "transports": ["stdout"]
  },
  "paths": {
    "contentPath": "content"
  }
}
EOF

echo "Ghost configuration created"
