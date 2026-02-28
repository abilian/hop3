#!/bin/bash
set -e
cd "$(dirname "$0")/.."

mkdir -p data logs conf/provisioning/datasources conf/provisioning/dashboards

# Create minimal config
if [ ! -f conf/custom.ini ]; then
    cat > conf/custom.ini << EOF
[server]
http_port = ${PORT:-8080}

[paths]
data = data
logs = logs

[security]
admin_user = ${GF_SECURITY_ADMIN_USER:-admin}
EOF
fi

echo "Grafana configuration ready"
