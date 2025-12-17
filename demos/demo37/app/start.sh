#!/bin/bash
# Startup script for WordPress with MySQL configuration

set -e

# Parse DATABASE_URL if provided
if [ -n "$DATABASE_URL" ]; then
    # Extract components from mysql://user:pass@host:port/database
    export WORDPRESS_DB_USER=$(echo "$DATABASE_URL" | sed -n 's|.*://\([^:]*\):.*|\1|p')
    export WORDPRESS_DB_PASSWORD=$(echo "$DATABASE_URL" | sed -n 's|.*://[^:]*:\([^@]*\)@.*|\1|p')
    export WORDPRESS_DB_HOST=$(echo "$DATABASE_URL" | sed -n 's|.*@\([^:/]*\).*|\1|p')
    DB_PORT=$(echo "$DATABASE_URL" | sed -n 's|.*:\([0-9]*\)/.*|\1|p')
    export WORDPRESS_DB_NAME=$(echo "$DATABASE_URL" | sed -n 's|.*/\([^?]*\).*|\1|p')

    # Include port in host if not default
    if [ -n "$DB_PORT" ] && [ "$DB_PORT" != "3306" ]; then
        export WORDPRESS_DB_HOST="${WORDPRESS_DB_HOST}:${DB_PORT}"
    fi
fi

# Set WordPress home and site URL from HOST_NAME
if [ -n "$HOST_NAME" ]; then
    export WORDPRESS_CONFIG_EXTRA="
define('WP_HOME', 'https://${HOST_NAME}');
define('WP_SITEURL', 'https://${HOST_NAME}');
define('FORCE_SSL_ADMIN', true);
"
fi

# Run the original WordPress entrypoint
exec docker-entrypoint.sh apache2-foreground
