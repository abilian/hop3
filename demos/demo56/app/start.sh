#!/bin/bash
# Startup script for Shlink with PostgreSQL configuration

set -e

echo "==> Starting Shlink"

cd /var/www/shlink

# Configure PostgreSQL from PG* environment variables
if [ -n "$PGHOST" ]; then
    export DB_DRIVER=postgres
    export DB_HOST="$PGHOST"
    export DB_PORT="${PGPORT:-5432}"
    export DB_NAME="${PGDATABASE:-shlink}"
    export DB_USER="${PGUSER:-shlink}"
    export DB_PASSWORD="$PGPASSWORD"

    echo "==> Database config:"
    echo "    Driver: PostgreSQL"
    echo "    Host: $DB_HOST"
    echo "    Port: $DB_PORT"
    echo "    Database: $DB_NAME"
fi

# Set default domain from HOST_NAME if available
if [ -n "$HOST_NAME" ]; then
    export DEFAULT_DOMAIN="$HOST_NAME"
    export IS_HTTPS_ENABLED=true
    echo "==> Domain: $DEFAULT_DOMAIN (HTTPS enabled)"
fi

# Run database migrations
echo "==> Running database migrations..."
php vendor/bin/doctrine-migrations migrate --no-interaction --all-or-nothing 2>/dev/null || true

# Clear cache
echo "==> Clearing cache..."
php vendor/bin/doctrine orm:clear-cache:metadata 2>/dev/null || true

# Start PHP built-in server
echo "==> Starting PHP server on port 8080..."
exec php -S 0.0.0.0:8080 -t public/
