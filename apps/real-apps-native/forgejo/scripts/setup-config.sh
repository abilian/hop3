#!/bin/bash
# Setup Forgejo configuration from environment variables

set -e

PORT="${PORT:-8080}"
DB_TYPE="${DB_TYPE:-postgres}"
DB_HOST="${PGHOST:-localhost}"
DB_PORT="${PGPORT:-5432}"
DB_NAME="${PGDATABASE:-forgejo}"
DB_USER="${PGUSER:-forgejo}"
DB_PASS="${PGPASSWORD:-}"

mkdir -p custom/conf

cat > custom/conf/app.ini << EOF
[server]
HTTP_PORT = ${PORT}
ROOT_URL = ${HOP3_PUBLIC_URL:-http://localhost:${PORT}}/
DISABLE_SSH = true

[database]
DB_TYPE = ${DB_TYPE}
HOST = ${DB_HOST}:${DB_PORT}
NAME = ${DB_NAME}
USER = ${DB_USER}
PASSWD = ${DB_PASS}

[repository]
ROOT = data/forgejo-repositories

[service]
DISABLE_REGISTRATION = true

[log]
MODE = console
LEVEL = Info

[security]
INSTALL_LOCK = true
SECRET_KEY = ${SECRET_KEY:?SECRET_KEY not injected (declare it as a stable [env] generate secret)}
INTERNAL_TOKEN = ${INTERNAL_TOKEN:?INTERNAL_TOKEN not injected (declare it as a stable [env] generate secret)}

[oauth2]
JWT_SECRET = ${JWT_SECRET:?JWT_SECRET not injected (declare it as a stable [env] generate secret)}
EOF

echo "Forgejo configuration created"
