#!/bin/bash
# Startup script for Shlink

set -e

echo "==> Starting Shlink"

cd /var/www/shlink

# Configure database based on available environment variables
if [ -n "$PGHOST" ]; then
    # PostgreSQL configuration from addon
    export DB_DRIVER=postgres
    export DB_HOST="$PGHOST"
    export DB_PORT="${PGPORT:-5432}"
    export DB_NAME="${PGDATABASE:-shlink}"
    export DB_USER="${PGUSER:-shlink}"
    export DB_PASSWORD="$PGPASSWORD"

    echo "==> Database config: PostgreSQL at $DB_HOST:$DB_PORT"
else
    # Use SQLite for demo simplicity
    export DB_DRIVER=sqlite
    echo "==> Database config: SQLite (demo mode)"
fi

# Set default domain from HOST_NAME if available
if [ -n "$HOST_NAME" ]; then
    export DEFAULT_DOMAIN="$HOST_NAME"
    export IS_HTTPS_ENABLED=true
    echo "==> Domain: $DEFAULT_DOMAIN (HTTPS enabled)"
else
    export DEFAULT_DOMAIN=localhost
    export IS_HTTPS_ENABLED=false
    echo "==> Domain: localhost (HTTP mode)"
fi

# Ensure data directories exist with proper permissions
mkdir -p data/cache data/log data/locks
chown -R www-data:www-data data/ 2>/dev/null || true

# Run database migrations using Shlink's bin/cli
echo "==> Running database migrations..."
if [ -f "bin/cli" ]; then
    php bin/cli db:migrate --no-interaction 2>&1 || echo "Note: Migrations may have already run"
fi

# Clear cache
echo "==> Clearing cache..."
rm -rf data/cache/* 2>/dev/null || true

# Start PHP built-in server
echo "==> Starting PHP server on port 8080..."
exec php -S 0.0.0.0:8080 -t public/
