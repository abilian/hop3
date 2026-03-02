#!/bin/bash
set -e

# Required environment variables - fail fast if not set
: "${PORT:?ERROR: PORT is required}"

# Optional with defaults (non-critical)
export RADICALE_DATA_DIR="${RADICALE_DATA_DIR:-/var/lib/radicale/collections}"

# Create default admin user if users file does not exist
if [ ! -f /etc/radicale/users ]; then
    # RADICALE_ADMIN_PASSWORD should be set by Hop3, default to random if not
    ADMIN_PASSWORD="${RADICALE_ADMIN_PASSWORD:-$(head -c 16 /dev/urandom | base64)}"
    htpasswd -bcB /etc/radicale/users admin "${ADMIN_PASSWORD}"
    chown radicale:radicale /etc/radicale/users
    echo "Created admin user (password was ${RADICALE_ADMIN_PASSWORD:+provided}${RADICALE_ADMIN_PASSWORD:-auto-generated})"
fi

# Update config with correct port
sed -i "s/hosts = 0.0.0.0:8080/hosts = 0.0.0.0:${PORT}/" /etc/radicale/config

# Ensure proper ownership
chown -R radicale:radicale /var/lib/radicale

# Run Radicale as radicale user
exec su radicale -c "/opt/radicale/bin/radicale --config /etc/radicale/config"
