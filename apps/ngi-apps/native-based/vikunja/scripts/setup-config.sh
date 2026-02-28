#!/bin/bash
set -e
cd "$(dirname "$0")/.."

if [ ! -f config.yml ]; then
    cat > config.yml << EOF
service:
  interface: ":${PORT:-8080}"
  frontendurl: "${VIKUNJA_FRONTEND_URL:-http://localhost:8080/}"

database:
  type: postgres
  host: ${PGHOST:-localhost}
  port: ${PGPORT:-5432}
  database: ${PGDATABASE:-vikunja}
  user: ${PGUSER:-vikunja}
  password: ${PGPASSWORD:-}

files:
  basepath: ./files
EOF
fi

echo "Vikunja configuration ready"
