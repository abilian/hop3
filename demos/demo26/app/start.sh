#!/bin/sh
set -e

echo "==> Starting Miniflux"

# Miniflux uses DATABASE_URL directly (Hop3 provides this)
if [ -n "$DATABASE_URL" ]; then
    # Add sslmode=disable if not present (for internal connections)
    case "$DATABASE_URL" in
        *sslmode=*)
            # sslmode already specified
            ;;
        *)
            export DATABASE_URL="${DATABASE_URL}?sslmode=disable"
            ;;
    esac
    echo "==> Database URL configured"
fi

# Run database migrations automatically
export RUN_MIGRATIONS=1

# Create admin user on first run
export CREATE_ADMIN=1
export ADMIN_USERNAME="${ADMIN_USERNAME:-admin}"
export ADMIN_PASSWORD="${ADMIN_PASSWORD:-admin123}"

# Listen on all interfaces
export LISTEN_ADDR="0.0.0.0:8080"

echo "==> Starting Miniflux server..."
exec /usr/bin/miniflux
