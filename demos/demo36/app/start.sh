#!/bin/bash
# Startup script for Kanboard with MySQL configuration

set -e

# Parse DATABASE_URL if provided
if [ -n "$DATABASE_URL" ]; then
    # Extract components from mysql://user:pass@host:port/database
    DB_DRIVER="mysql"
    DB_USER=$(echo "$DATABASE_URL" | sed -n 's|.*://\([^:]*\):.*|\1|p')
    DB_PASSWORD=$(echo "$DATABASE_URL" | sed -n 's|.*://[^:]*:\([^@]*\)@.*|\1|p')
    DB_HOST=$(echo "$DATABASE_URL" | sed -n 's|.*@\([^:/]*\).*|\1|p')
    DB_PORT=$(echo "$DATABASE_URL" | sed -n 's|.*:\([0-9]*\)/.*|\1|p')
    DB_NAME=$(echo "$DATABASE_URL" | sed -n 's|.*/\([^?]*\).*|\1|p')

    # Default port if not specified
    DB_PORT=${DB_PORT:-3306}

    # Export for Kanboard
    export DB_DRIVER
    export DB_USERNAME="$DB_USER"
    export DB_PASSWORD
    export DB_HOSTNAME="$DB_HOST"
    export DB_PORT
    export DB_NAME
fi

# Start the application (nginx + php-fpm)
exec /usr/local/bin/entrypoint.sh
