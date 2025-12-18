#!/bin/bash
# Startup script for EasyAppointments with MySQL configuration

set -e

echo "==> Starting EasyAppointments"

cd /var/www/html

# Create config.php from environment variables if MySQL is configured
if [ -n "$MYSQL_HOST" ] && [ ! -f /var/www/html/config.php ]; then
    echo "==> Creating EasyAppointments configuration"

    # Copy sample config if it exists
    if [ -f /var/www/html/config-sample.php ]; then
        cp /var/www/html/config-sample.php /var/www/html/config.php
    fi

    # Update database settings
    if [ -f /var/www/html/config.php ]; then
        sed -i "s|const DB_HOST = '.*';|const DB_HOST = '${MYSQL_HOST}';|" /var/www/html/config.php
        sed -i "s|const DB_NAME = '.*';|const DB_NAME = '${MYSQL_DATABASE}';|" /var/www/html/config.php
        sed -i "s|const DB_USERNAME = '.*';|const DB_USERNAME = '${MYSQL_USER}';|" /var/www/html/config.php
        sed -i "s|const DB_PASSWORD = '.*';|const DB_PASSWORD = '${MYSQL_PASSWORD}';|" /var/www/html/config.php

        # Set base URL if HOST_NAME is provided
        if [ -n "$HOST_NAME" ]; then
            sed -i "s|const BASE_URL = '.*';|const BASE_URL = 'https://${HOST_NAME}';|" /var/www/html/config.php
        fi
    fi

    chown www-data:www-data /var/www/html/config.php

    echo "==> Database config:"
    echo "    Host: ${MYSQL_HOST}"
    echo "    User: ${MYSQL_USER}"
    echo "    Database: ${MYSQL_DATABASE}"
fi

# Ensure storage directory is writable
mkdir -p /var/www/html/storage/logs /var/www/html/storage/sessions /var/www/html/storage/uploads
chown -R www-data:www-data /var/www/html/storage 2>/dev/null || true

echo "==> Starting Apache..."
exec apache2ctl -D FOREGROUND
