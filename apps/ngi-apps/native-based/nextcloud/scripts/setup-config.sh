#!/bin/bash
set -e

# Run Nextcloud installer if not already installed
if [ ! -f config/config.php ]; then
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
fi

echo "Nextcloud configuration ready"
