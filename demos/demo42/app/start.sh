#!/bin/bash
# Startup script for LimeSurvey with MySQL configuration

set -e

echo "==> Starting LimeSurvey"

cd /var/www/html

# Create config.php from environment variables if MySQL is configured
if [ -n "$MYSQL_HOST" ] && [ ! -f /var/www/html/application/config/config.php ]; then
    echo "==> Creating LimeSurvey configuration"

    cat > /var/www/html/application/config/config.php << PHPEOF
<?php if (!defined('BASEPATH')) exit('No direct script access allowed');
return array(
    'components' => array(
        'db' => array(
            'connectionString' => 'mysql:host=${MYSQL_HOST};port=${MYSQL_PORT:-3306};dbname=${MYSQL_DATABASE};',
            'username' => '${MYSQL_USER}',
            'password' => '${MYSQL_PASSWORD}',
            'charset' => 'utf8mb4',
            'tablePrefix' => 'lime_',
        ),
        'urlManager' => array(
            'urlFormat' => 'path',
            'rules' => array(),
            'showScriptName' => true,
        ),
    ),
    'config' => array(
        'debug' => 0,
        'debugsql' => 0,
    )
);
PHPEOF

    chown www-data:www-data /var/www/html/application/config/config.php

    echo "==> Database config:"
    echo "    Host: ${MYSQL_HOST}"
    echo "    Port: ${MYSQL_PORT:-3306}"
    echo "    User: ${MYSQL_USER}"
    echo "    Database: ${MYSQL_DATABASE}"
fi

# Ensure directories are writable
chown -R www-data:www-data /var/www/html/tmp /var/www/html/upload /var/www/html/application/config 2>/dev/null || true

echo "==> Starting Apache..."
exec apache2ctl -D FOREGROUND
