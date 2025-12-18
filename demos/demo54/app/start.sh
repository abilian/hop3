#!/bin/bash
# Startup script for Miniflux with PostgreSQL configuration

set -e

echo "==> Starting Miniflux"

cd /app

# Configure DATABASE_URL from PG* environment variables if not set
if [ -z "$DATABASE_URL" ] && [ -n "$PGHOST" ]; then
    export DATABASE_URL="postgres://${PGUSER:-miniflux}:${PGPASSWORD}@${PGHOST}:${PGPORT:-5432}/${PGDATABASE:-miniflux}?sslmode=disable"
    echo "==> Database URL configured from PG* variables"
fi

if [ -n "$DATABASE_URL" ]; then
    echo "==> Database config:"
    # Extract and display host (without password)
    DB_HOST=$(echo "$DATABASE_URL" | sed -n 's|.*@\([^:/]*\).*|\1|p')
    echo "    Host: $DB_HOST"
fi

# Set admin credentials if provided via environment
if [ -n "$MINIFLUX_ADMIN_USER" ] && [ -n "$MINIFLUX_ADMIN_PASSWORD" ]; then
    export CREATE_ADMIN=1
    export ADMIN_USERNAME="$MINIFLUX_ADMIN_USER"
    export ADMIN_PASSWORD="$MINIFLUX_ADMIN_PASSWORD"
    echo "==> Admin user will be created: $ADMIN_USERNAME"
fi

# Default admin if none specified
if [ -z "$ADMIN_USERNAME" ]; then
    export CREATE_ADMIN=1
    export ADMIN_USERNAME="admin"
    export ADMIN_PASSWORD="changeme123"
    echo "==> Using default admin credentials (admin/changeme123)"
fi

echo "==> Running migrations and starting Miniflux..."
exec /app/miniflux
