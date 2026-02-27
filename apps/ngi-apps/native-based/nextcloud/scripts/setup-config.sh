#!/bin/bash

# Ensure we're in the Nextcloud directory
cd "$(dirname "$0")/.."

# Check if Nextcloud is properly installed
if php occ status 2>/dev/null | grep -q "installed: true"; then
    echo "Nextcloud already installed"
    echo "Nextcloud configuration ready"
    exit 0
fi

echo "Installing Nextcloud..."

# Run installer
php occ maintenance:install \
    --database="mysql" \
    --database-host="${MYSQL_HOST:-localhost}" \
    --database-port="${MYSQL_PORT:-3306}" \
    --database-name="${MYSQL_DATABASE:-nextcloud}" \
    --database-user="${MYSQL_USER:-nextcloud}" \
    --database-pass="${MYSQL_PASSWORD:-}" \
    --admin-user="${NEXTCLOUD_ADMIN_USER:-admin}" \
    --admin-pass="${NEXTCLOUD_ADMIN_PASSWORD:-changeme}" \
    --data-dir="$(pwd)/data"

# Trust localhost
php occ config:system:set trusted_domains 0 --value="localhost"

echo "Nextcloud installed successfully"
echo "Nextcloud configuration ready"
