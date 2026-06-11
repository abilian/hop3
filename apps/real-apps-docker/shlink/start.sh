#!/bin/bash
# Startup script for Shlink

set -e

echo "==> Starting Shlink 4.3.1"

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
    # Use SQLite by default
    export DB_DRIVER=sqlite
    echo "==> Database config: SQLite"
fi

# Set default domain from HOST_NAME or DEFAULT_DOMAIN
if [ -n "$DEFAULT_DOMAIN" ]; then
    echo "==> Domain: $DEFAULT_DOMAIN"
elif [ -n "$HOST_NAME" ]; then
    export DEFAULT_DOMAIN="$HOST_NAME"
    export IS_HTTPS_ENABLED=true
    echo "==> Domain: $DEFAULT_DOMAIN (HTTPS enabled)"
else
    export DEFAULT_DOMAIN=localhost
    export IS_HTTPS_ENABLED=false
    echo "==> Domain: localhost (HTTP mode)"
fi

# Skip GeoLite download for faster startup
export SKIP_INITIAL_GEOLITE_DOWNLOAD=true

# Ensure data directories exist with proper permissions
mkdir -p data/cache data/log data/locks data/db
chmod -R 777 data/ 2>/dev/null || true

# Clear cache
echo "==> Clearing cache..."
rm -rf data/cache/* 2>/dev/null || true

# Show available CLI commands for debugging
echo "==> Available CLI commands:"
php bin/cli list 2>&1 | head -30 || true

# Run database setup
echo "==> Running database setup..."
if [ -f "bin/cli" ]; then
    # First try db:create (creates database schema)
    echo "==> Creating database..."
    php bin/cli db:create 2>&1 || echo "Note: db:create may not exist or schema already created"

    # Then run migrations
    echo "==> Running migrations..."
    php bin/cli db:migrate --no-interaction 2>&1 || echo "Note: Migrations may have completed or failed"
fi

# Clear cache after setup
echo "==> Clearing cache..."
rm -rf data/cache/* 2>/dev/null || true

# Start PHP built-in server
echo "==> Starting PHP server on port 8080..."
exec php -S 0.0.0.0:8080 -t public/
