#!/bin/bash

# Ensure we're in the Nextcloud directory
cd "$(dirname "$0")/.."

# Install once (idempotent: skip when already installed).
if php occ status 2>/dev/null | grep -q "installed: true"; then
    echo "Nextcloud already installed"
else
    echo "Installing Nextcloud..."
    php occ maintenance:install \
        --database="mysql" \
        --database-host="${MYSQL_HOST:-localhost}" \
        --database-port="${MYSQL_PORT:-3306}" \
        --database-name="${MYSQL_DATABASE:-nextcloud}" \
        --database-user="${MYSQL_USER:-nextcloud}" \
        --database-pass="${MYSQL_PASSWORD:-}" \
        --admin-user="${NEXTCLOUD_ADMIN_USER:?NEXTCLOUD_ADMIN_USER is required (set via [admin] username + [env.computed])}" \
        --admin-pass="${NEXTCLOUD_ADMIN_PASSWORD:?NEXTCLOUD_ADMIN_PASSWORD is required (set via [admin] password generate + [env.computed])}" \
        --data-dir="$(pwd)/data"
    echo "Nextcloud installed successfully"
fi

# Trust the loopback AND the public hostname(s) Hop3 assigned — re-applied every
# deploy so a domain change takes effect. Without the real host in
# trusted_domains, Nextcloud rejects every request through the reverse proxy
# with "Access through untrusted domain" (HTTP 400) and the login is unreachable.
php occ config:system:set trusted_domains 0 --value="localhost"
if [ -n "${HOST_NAME:-}" ] && [ "${HOST_NAME}" != "_" ]; then
    i=1
    for host in ${HOST_NAME//,/ }; do
        php occ config:system:set trusted_domains "$i" --value="$host"
        i=$((i + 1))
    done
fi

echo "Nextcloud configuration ready"
