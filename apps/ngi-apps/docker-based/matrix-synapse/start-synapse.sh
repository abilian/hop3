#!/bin/bash
set -e

# Required environment variables - fail fast if not set
: "${PORT:?ERROR: PORT is required}"
: "${PGHOST:?ERROR: PGHOST is required}"
: "${PGPORT:?ERROR: PGPORT is required}"
: "${PGDATABASE:?ERROR: PGDATABASE is required}"
: "${PGUSER:?ERROR: PGUSER is required}"
: "${PGPASSWORD:?ERROR: PGPASSWORD is required}"

DATA_DIR=/home/synapse/data

# Generate homeserver.yaml if not exists
if [ ! -f "$DATA_DIR/homeserver.yaml" ]; then
    /home/synapse/venv/bin/python -m synapse.app.homeserver \
        --server-name "${SERVER_NAME:-localhost}" \
        --config-path "$DATA_DIR/homeserver.yaml" \
        --generate-config \
        --report-stats no \
        --data-directory "$DATA_DIR"
fi

# Override database configuration for PostgreSQL
cat > "$DATA_DIR/database.yaml" << EOFDB
database:
  name: psycopg2
  allow_unsafe_locale: true
  args:
    host: $PGHOST
    port: $PGPORT
    database: $PGDATABASE
    user: $PGUSER
    password: $PGPASSWORD
    cp_min: 5
    cp_max: 10
EOFDB

# Set port and bind address in config (bind to 0.0.0.0 for Docker)
sed -i "s/port: 8008/port: $PORT/" "$DATA_DIR/homeserver.yaml"
sed -i "s/- ::1/- 0.0.0.0/" "$DATA_DIR/homeserver.yaml"
sed -i "/- 127.0.0.1/d" "$DATA_DIR/homeserver.yaml"

# Start Synapse with both config files
chown -R synapse:synapse "$DATA_DIR"
exec su synapse -c "/home/synapse/venv/bin/python -m synapse.app.homeserver --config-path $DATA_DIR/homeserver.yaml --config-path $DATA_DIR/database.yaml"
