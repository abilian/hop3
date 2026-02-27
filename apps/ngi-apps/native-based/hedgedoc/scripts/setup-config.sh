#!/bin/bash
set -e

# Ensure we're in the HedgeDoc directory
cd "$(dirname "$0")/.."

echo "Creating HedgeDoc configuration..."
cat > config.json << EOF
{
  "production": {
    "host": "0.0.0.0",
    "port": ${PORT:-8080},
    "db": {
      "dialect": "postgres",
      "host": "${PGHOST:-localhost}",
      "port": ${PGPORT:-5432},
      "database": "${PGDATABASE:-hedgedoc}",
      "username": "${PGUSER:-hedgedoc}",
      "password": "${PGPASSWORD:-}"
    },
    "sessionSecret": "$(head -c 32 /dev/urandom | base64)",
    "allowAnonymous": true,
    "allowAnonymousEdits": true,
    "defaultPermission": "freely"
  }
}
EOF

# Note: HedgeDoc uses Umzug and runs database migrations automatically on startup
echo "HedgeDoc configuration created successfully"
