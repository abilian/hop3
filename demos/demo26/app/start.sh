#!/bin/sh
set -e

echo "==> Starting Miniflux"

# Convert postgresql:// to postgres:// if needed (Miniflux requires postgres://)
if [ -n "$DATABASE_URL" ]; then
    export DATABASE_URL=$(echo "$DATABASE_URL" | sed 's|^postgresql://|postgres://|')

    # Add sslmode=disable if not present (for internal connections)
    case "$DATABASE_URL" in
        *sslmode=*)
            ;;
        *\?*)
            export DATABASE_URL="${DATABASE_URL}&sslmode=disable"
            ;;
        *)
            export DATABASE_URL="${DATABASE_URL}?sslmode=disable"
            ;;
    esac
    echo "==> Database configured"
fi

# Enable auto-migration and admin creation
export RUN_MIGRATIONS=1
export CREATE_ADMIN=1
export ADMIN_USERNAME="${ADMIN_USERNAME:-admin}"
export ADMIN_PASSWORD="${ADMIN_PASSWORD:-admin123}"

# Bind to all interfaces
export LISTEN_ADDR="0.0.0.0:8080"

echo "==> Starting Miniflux server on $LISTEN_ADDR..."
exec /app/miniflux
