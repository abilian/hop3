#!/bin/bash
set -e

# Validate required environment variables (injected by Hop3)
: "${PORT:?ERROR: PORT is required}"

# Optional with defaults
GF_PATHS_DATA="${GF_PATHS_DATA:-/var/lib/grafana}"
GF_PATHS_LOGS="${GF_PATHS_LOGS:-/var/log/grafana}"
GF_PATHS_PROVISIONING="${GF_PATHS_PROVISIONING:-/etc/grafana/provisioning}"
GF_SECURITY_ADMIN_USER="${GF_SECURITY_ADMIN_USER:-admin}"
GF_SECURITY_ADMIN_PASSWORD="${GF_SECURITY_ADMIN_PASSWORD:-admin}"

# Export for Grafana
export GF_SERVER_HTTP_PORT="${PORT}"
export GF_PATHS_DATA
export GF_PATHS_LOGS
export GF_PATHS_PROVISIONING
export GF_SECURITY_ADMIN_USER
export GF_SECURITY_ADMIN_PASSWORD

# Ensure proper ownership
chown -R grafana:grafana /var/lib/grafana /var/log/grafana

# Run Grafana as grafana user
exec su grafana -s /bin/bash -c "/usr/share/grafana/bin/grafana-server \
    --homepath=/usr/share/grafana \
    --config=/usr/share/grafana/conf/defaults.ini \
    cfg:default.paths.data=${GF_PATHS_DATA} \
    cfg:default.paths.logs=${GF_PATHS_LOGS} \
    cfg:default.paths.provisioning=${GF_PATHS_PROVISIONING}"
