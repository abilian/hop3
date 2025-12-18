#!/bin/bash
# Startup script for WordPress with MySQL configuration

set -e

echo "==> Starting WordPress"

cd /var/www/html

# Parse DATABASE_URL if provided
if [ -n "$DATABASE_URL" ]; then
    DB_USER=$(echo "$DATABASE_URL" | sed -n 's|.*://\([^:]*\):.*|\1|p')
    DB_PASSWORD=$(echo "$DATABASE_URL" | sed -n 's|.*://[^:]*:\([^@]*\)@.*|\1|p')
    DB_HOST=$(echo "$DATABASE_URL" | sed -n 's|.*@\([^:/]*\).*|\1|p')
    DB_PORT=$(echo "$DATABASE_URL" | sed -n 's|.*:\([0-9]*\)/.*|\1|p')
    DB_NAME=$(echo "$DATABASE_URL" | sed -n 's|.*/\([^?]*\).*|\1|p')
    DB_PORT=${DB_PORT:-3306}

    echo "==> Database config:"
    echo "    Host: $DB_HOST"
    echo "    Port: $DB_PORT"
    echo "    User: $DB_USER"
    echo "    Database: $DB_NAME"

    # Create wp-config.php if it doesn't exist
    if [ ! -f wp-config.php ]; then
        echo "==> Creating wp-config.php"

        # Escape single quotes in password for PHP
        DB_PASSWORD_ESCAPED=$(echo "$DB_PASSWORD" | sed "s/'/\\\\'/g")

        # Generate salts
        SALTS=$(curl -s https://api.wordpress.org/secret-key/1.1/salt/)

        cat > wp-config.php << WPEOF
<?php
define('DB_NAME', '${DB_NAME}');
define('DB_USER', '${DB_USER}');
define('DB_PASSWORD', '${DB_PASSWORD_ESCAPED}');
define('DB_HOST', '${DB_HOST}:${DB_PORT}');
define('DB_CHARSET', 'utf8mb4');
define('DB_COLLATE', '');

${SALTS}

\$table_prefix = 'wp_';

define('WP_DEBUG', false);

WPEOF

        # Add site URL if HOST_NAME is set
        if [ -n "$HOST_NAME" ]; then
            cat >> wp-config.php << WPEOF
define('WP_HOME', 'https://${HOST_NAME}');
define('WP_SITEURL', 'https://${HOST_NAME}');
define('FORCE_SSL_ADMIN', true);
WPEOF
        fi

        # Add the final require statement
        cat >> wp-config.php << 'WPEOF'

if ( ! defined( 'ABSPATH' ) ) {
    define( 'ABSPATH', __DIR__ . '/' );
}

require_once ABSPATH . 'wp-settings.php';
WPEOF

        chown www-data:www-data wp-config.php
    fi
else
    echo "==> WARNING: No DATABASE_URL provided. WordPress needs a database."
fi

echo "==> Starting Apache..."
exec apache2ctl -D FOREGROUND
