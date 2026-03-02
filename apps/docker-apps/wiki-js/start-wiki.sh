#!/bin/bash
set -e

# Validate required environment variables (injected by Hop3)
: "${PORT:?ERROR: PORT is required}"
: "${PGHOST:?ERROR: PGHOST is required}"
: "${PGPORT:?ERROR: PGPORT is required}"
: "${PGDATABASE:?ERROR: PGDATABASE is required}"
: "${PGUSER:?ERROR: PGUSER is required}"
: "${PGPASSWORD:?ERROR: PGPASSWORD is required}"

cd /home/wiki/app

# Generate config.yml from environment variables
cat > config.yml << EOF
port: ${PORT}
db:
  type: postgres
  host: ${PGHOST}
  port: ${PGPORT}
  user: ${PGUSER}
  pass: ${PGPASSWORD}
  db: ${PGDATABASE}
bindIP: 0.0.0.0
logLevel: info
EOF

chown wiki:wiki config.yml

# Run as wiki user
exec su wiki -c "cd /home/wiki/app && node server"
