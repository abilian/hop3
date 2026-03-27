#!/bin/bash
# Startup script for EasyAppointments with MySQL configuration

set -e

echo "==> Starting EasyAppointments"

cd /var/www/html

# Always create config.php from sample if it doesn't exist
if [ ! -f /var/www/html/config.php ]; then
    echo "==> Creating config.php from config-sample.php"
    if [ -f /var/www/html/config-sample.php ]; then
        cp /var/www/html/config-sample.php /var/www/html/config.php
    else
        echo "ERROR: config-sample.php not found!"
        exit 1
    fi
fi

# Parse DATABASE_URL into individual vars if set (hop3 addon format)
# Format: mysql://user:password@host:port/dbname
if [ -n "$DATABASE_URL" ] && [ -z "$MYSQL_HOST" ]; then
    echo "==> Parsing DATABASE_URL"
    # Strip protocol prefix
    DB_URL_BODY="${DATABASE_URL#mysql://}"
    DB_URL_BODY="${DB_URL_BODY#mysqli://}"

    # Extract user:password@host:port/dbname
    MYSQL_USER="${DB_URL_BODY%%:*}"
    DB_URL_BODY="${DB_URL_BODY#*:}"
    MYSQL_PASSWORD="${DB_URL_BODY%%@*}"
    DB_URL_BODY="${DB_URL_BODY#*@}"
    MYSQL_HOST="${DB_URL_BODY%%:*}"
    DB_URL_BODY="${DB_URL_BODY#*:}"
    MYSQL_PORT="${DB_URL_BODY%%/*}"
    MYSQL_DATABASE="${DB_URL_BODY#*/}"
    # Strip any query string from database name
    MYSQL_DATABASE="${MYSQL_DATABASE%%\?*}"

    export MYSQL_HOST MYSQL_PORT MYSQL_USER MYSQL_PASSWORD MYSQL_DATABASE
fi

# Update database settings if MySQL is configured
if [ -n "$MYSQL_HOST" ]; then
    echo "==> Configuring database settings"
    sed -i "s|const DB_HOST = '.*';|const DB_HOST = '${MYSQL_HOST}';|" /var/www/html/config.php
    sed -i "s|const DB_NAME = '.*';|const DB_NAME = '${MYSQL_DATABASE}';|" /var/www/html/config.php
    sed -i "s|const DB_USERNAME = '.*';|const DB_USERNAME = '${MYSQL_USER}';|" /var/www/html/config.php
    sed -i "s|const DB_PASSWORD = '.*';|const DB_PASSWORD = '${MYSQL_PASSWORD}';|" /var/www/html/config.php

    echo "==> Database config:"
    echo "    Host: ${MYSQL_HOST}"
    echo "    User: ${MYSQL_USER}"
    echo "    Database: ${MYSQL_DATABASE}"
fi

# Set base URL if HOST_NAME is provided
if [ -n "$HOST_NAME" ]; then
    sed -i "s|const BASE_URL = '.*';|const BASE_URL = 'https://${HOST_NAME}';|" /var/www/html/config.php
fi

chown www-data:www-data /var/www/html/config.php

# Ensure storage directory is writable
mkdir -p /var/www/html/storage/logs /var/www/html/storage/sessions /var/www/html/storage/uploads
chown -R www-data:www-data /var/www/html/storage 2>/dev/null || true

echo "==> Starting Apache..."
exec apache2ctl -D FOREGROUND
