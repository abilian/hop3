#!/bin/sh
set -e

echo "==> Starting OpenCloud"

# Ensure data directories exist
mkdir -p /app/data/config /app/data/data

# Initialize OpenCloud if not already done
if [ ! -f /app/data/config/opencloud.yaml ]; then
    echo "==> Initializing OpenCloud..."
    /app/opencloud init --insecure true --admin-password changeme
fi

# Set domain from Hop3 environment
if [ -n "$HOST_NAME" ]; then
    export OC_DOMAIN="$HOST_NAME"
    export OC_URL="https://$HOST_NAME"
fi

# Allow HTTP connections (nginx handles TLS)
export OC_INSECURE=true
export PROXY_TLS=false

# Add notifications service
export OC_ADD_RUN_SERVICES="notifications"

echo "==> Starting OpenCloud server..."
exec /app/opencloud server
