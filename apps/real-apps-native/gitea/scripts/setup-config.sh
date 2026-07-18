#!/bin/bash
# Setup Gitea configuration from environment variables

set -e

PORT="${PORT:-8080}"
DB_TYPE="${DB_TYPE:-postgres}"
DB_HOST="${PGHOST:-localhost}"
DB_PORT="${PGPORT:-5432}"
DB_NAME="${PGDATABASE:-gitea}"
DB_USER="${PGUSER:-gitea}"
DB_PASS="${PGPASSWORD:-}"

mkdir -p custom/conf

cat > custom/conf/app.ini << EOF
[server]
HTTP_PORT = ${PORT}
ROOT_URL = http://localhost:${PORT}/

[database]
DB_TYPE = ${DB_TYPE}
HOST = ${DB_HOST}:${DB_PORT}
NAME = ${DB_NAME}
USER = ${DB_USER}
PASSWD = ${DB_PASS}

[repository]
ROOT = data/gitea-repositories

[service]
; Disable open registration so a stranger can't seize the first-admin slot;
; Hop3 provisions the intended admin via [admin].create.
DISABLE_REGISTRATION = true

[log]
MODE = console
LEVEL = Info

[security]
INSTALL_LOCK = true
SECRET_KEY = $(head -c 32 /dev/urandom | base64)
EOF

echo "Gitea configuration created"
