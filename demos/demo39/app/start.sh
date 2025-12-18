#!/bin/bash
# Startup script for Matomo with MySQL configuration

set -e

echo "==> Starting Matomo"

cd /var/www/html

# Create config directory if needed
mkdir -p /var/www/html/config
chown www-data:www-data /var/www/html/config

# Map MYSQL_* variables (from Hop3 addon) to MATOMO_DATABASE_* variables
if [ -n "$MYSQL_HOST" ]; then
    export MATOMO_DATABASE_HOST="${MYSQL_HOST}"
fi
if [ -n "$MYSQL_PORT" ]; then
    export MATOMO_DATABASE_PORT="${MYSQL_PORT}"
fi
if [ -n "$MYSQL_USER" ]; then
    export MATOMO_DATABASE_USERNAME="$MYSQL_USER"
fi
if [ -n "$MYSQL_PASSWORD" ]; then
    export MATOMO_DATABASE_PASSWORD="$MYSQL_PASSWORD"
fi
if [ -n "$MYSQL_DATABASE" ]; then
    export MATOMO_DATABASE_DBNAME="$MYSQL_DATABASE"
fi
export MATOMO_DATABASE_ADAPTER="mysql"

echo "==> Database config:"
echo "    Host: ${MATOMO_DATABASE_HOST:-not set}"
echo "    Port: ${MATOMO_DATABASE_PORT:-3306}"
echo "    User: ${MATOMO_DATABASE_USERNAME:-not set}"
echo "    Database: ${MATOMO_DATABASE_DBNAME:-not set}"

# Create config.ini.php if database is configured and config doesn't exist
if [ -n "$MYSQL_HOST" ] && [ ! -f /var/www/html/config/config.ini.php ]; then
    echo "==> Creating initial config.ini.php"
    cat > /var/www/html/config/config.ini.php << EOF
[database]
host = "${MATOMO_DATABASE_HOST}"
port = "${MATOMO_DATABASE_PORT:-3306}"
username = "${MATOMO_DATABASE_USERNAME}"
password = "${MATOMO_DATABASE_PASSWORD}"
dbname = "${MATOMO_DATABASE_DBNAME}"
tables_prefix = "matomo_"
charset = "utf8mb4"

[General]
force_ssl = 1
proxy_client_headers[] = HTTP_X_FORWARDED_FOR
EOF
    chown www-data:www-data /var/www/html/config/config.ini.php
fi

echo "==> Starting Apache..."
exec apache2ctl -D FOREGROUND
