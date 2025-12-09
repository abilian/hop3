#!/bin/bash
set -eu -o pipefail

mkdir -p /app/data /app/config

# Initialize OpenCloud if not already done
if [[ ! -f /app/config/opencloud.yaml ]]; then
    echo "==> Initializing OpenCloud"
    /app/opencloud init --insecure true --admin-password "${ADMIN_PASSWORD:-admin}"
fi

# Configure OpenCloud
export OC_DOMAIN="${HOST_NAME:-localhost}"
export OC_URL="https://${HOST_NAME:-localhost}"
export OC_INSECURE=true
export PROXY_TLS=false

# Disable notifications service (requires SMTP configuration)
# To enable notifications, set NOTIFICATIONS_SMTP_* environment variables
# export OC_ADD_RUN_SERVICES="notifications"

echo "==> Starting OpenCloud on port 9200"
echo "    Domain: ${OC_DOMAIN}"
echo "    URL: ${OC_URL}"
echo "    Admin password: ${ADMIN_PASSWORD:-admin}"

exec /app/opencloud server
