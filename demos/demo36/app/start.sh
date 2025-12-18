#!/bin/bash
# Startup script for Kanboard with MySQL configuration

set -e

echo "==> Starting Kanboard"

# Create config.php from environment variables
CONFIG_FILE="/var/www/kanboard/config.php"

cat > "$CONFIG_FILE" << 'PHPEOF'
<?php

// Database configuration from environment
if (getenv('DATABASE_URL')) {
    $url = parse_url(getenv('DATABASE_URL'));

    // Determine driver from scheme
    $scheme = $url['scheme'] ?? 'sqlite';
    if ($scheme === 'mysql' || $scheme === 'mariadb') {
        define('DB_DRIVER', 'mysql');
    } elseif ($scheme === 'postgres' || $scheme === 'postgresql') {
        define('DB_DRIVER', 'postgres');
    } else {
        define('DB_DRIVER', 'sqlite');
    }

    if (DB_DRIVER !== 'sqlite') {
        define('DB_USERNAME', $url['user'] ?? '');
        define('DB_PASSWORD', $url['pass'] ?? '');
        define('DB_HOSTNAME', $url['host'] ?? 'localhost');
        define('DB_PORT', $url['port'] ?? (DB_DRIVER === 'mysql' ? '3306' : '5432'));
        define('DB_NAME', ltrim($url['path'] ?? '', '/'));
    }
} else {
    define('DB_DRIVER', 'sqlite');
}

// Enable debug mode for development
define('DEBUG', true);

// Enable plugins
define('PLUGIN_INSTALLER', true);

// Logging
define('LOG_DRIVER', 'stdout');

// Session
define('SESSION_HANDLER', 'php');
PHPEOF

chown www-data:www-data "$CONFIG_FILE"

echo "==> Database driver: $(grep "define('DB_DRIVER'" "$CONFIG_FILE" | head -1)"
echo "==> Starting nginx and php-fpm via supervisor..."

exec /usr/bin/supervisord -c /etc/supervisor/conf.d/supervisord.conf
