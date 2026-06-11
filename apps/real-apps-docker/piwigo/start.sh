#!/bin/bash
# Startup script for Piwigo with MySQL configuration

set -e

echo "==> Starting Piwigo"

cd /var/www/html

# Create local config if database is configured
if [ -n "$MYSQL_HOST" ] && [ ! -f /var/www/html/local/config/database.inc.php ]; then
    echo "==> Creating database configuration"
    mkdir -p /var/www/html/local/config

    cat > /var/www/html/local/config/database.inc.php << PHPEOF
<?php
\$conf['dblayer'] = 'mysqli';
\$conf['db_base'] = '${MYSQL_DATABASE}';
\$conf['db_user'] = '${MYSQL_USER}';
\$conf['db_password'] = '${MYSQL_PASSWORD}';
\$conf['db_host'] = '${MYSQL_HOST}';
\$conf['db_port'] = '${MYSQL_PORT:-3306}';
\$conf['db_prefix'] = 'piwigo_';
PHPEOF

    chown www-data:www-data /var/www/html/local/config/database.inc.php

    echo "==> Database config:"
    echo "    Host: ${MYSQL_HOST}"
    echo "    Port: ${MYSQL_PORT:-3306}"
    echo "    User: ${MYSQL_USER}"
    echo "    Database: ${MYSQL_DATABASE}"
fi

# Ensure directories are writable
chown -R www-data:www-data /var/www/html/_data /var/www/html/galleries /var/www/html/upload /var/www/html/local 2>/dev/null || true

echo "==> Starting Apache..."
exec apache2ctl -D FOREGROUND
