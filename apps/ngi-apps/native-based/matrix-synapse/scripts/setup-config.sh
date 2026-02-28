#!/bin/bash
set -e
cd "$(dirname "$0")/.."

if [ ! -f homeserver.yaml ]; then
    python -m synapse.app.homeserver \
        --server-name "${SERVER_NAME:-localhost}" \
        --config-path homeserver.yaml \
        --generate-config \
        --report-stats=no

    # Configure PostgreSQL with allow_unsafe_locale for non-C locale databases
    cat >> homeserver.yaml << EOF

database:
  name: psycopg2
  args:
    user: ${PGUSER:-synapse}
    password: ${PGPASSWORD:-}
    database: ${PGDATABASE:-synapse}
    host: ${PGHOST:-localhost}
    port: ${PGPORT:-5432}
    cp_min: 5
    cp_max: 10
  allow_unsafe_locale: true
EOF

    # Configure the HTTP listener to bind to the correct port
    sed -i "s/port: 8008/port: ${PORT:-8008}/" homeserver.yaml
fi

echo "Matrix Synapse configuration ready"
