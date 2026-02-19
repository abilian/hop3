#!/bin/bash
set -e

cat > config.toml << EOF
[app]
address = "0.0.0.0:${PORT:-8080}"
admin_username = "admin"
admin_password = "changeme"

[db]
host = "${PGHOST:-localhost}"
port = ${PGPORT:-5432}
user = "${PGUSER:-listmonk}"
password = "${PGPASSWORD:-}"
database = "${PGDATABASE:-listmonk}"
ssl_mode = "disable"
max_open = 25
max_idle = 25
max_lifetime = "300s"
EOF

# Initialize database if needed
./listmonk --install --yes 2>/dev/null || true

echo "Listmonk configuration created"
