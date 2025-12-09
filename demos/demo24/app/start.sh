#!/bin/sh
set -e

echo "==> Starting Listmonk"

# Parse DATABASE_URL to extract components
# Format: postgresql://user:password@host:port/database
if [ -n "$DATABASE_URL" ]; then
    # Remove the postgresql:// prefix
    DB_CONN=$(echo "$DATABASE_URL" | sed 's|postgresql://||')

    # Extract user:password
    DB_USERPASS=$(echo "$DB_CONN" | cut -d@ -f1)
    export LISTMONK_db__user=$(echo "$DB_USERPASS" | cut -d: -f1)
    export LISTMONK_db__password=$(echo "$DB_USERPASS" | cut -d: -f2)

    # Extract host:port/database
    DB_HOSTDB=$(echo "$DB_CONN" | cut -d@ -f2)
    DB_HOSTPORT=$(echo "$DB_HOSTDB" | cut -d/ -f1)
    export LISTMONK_db__host=$(echo "$DB_HOSTPORT" | cut -d: -f1)
    export LISTMONK_db__port=$(echo "$DB_HOSTPORT" | cut -d: -f2)
    export LISTMONK_db__database=$(echo "$DB_HOSTDB" | cut -d/ -f2)

    echo "==> Database config:"
    echo "    Host: $LISTMONK_db__host"
    echo "    Port: $LISTMONK_db__port"
    echo "    User: $LISTMONK_db__user"
    echo "    Database: $LISTMONK_db__database"
fi

# Set SSL mode (disable for internal connections)
export LISTMONK_db__ssl_mode="disable"

# Bind to all interfaces on port 9000
export LISTMONK_app__address="0.0.0.0:9000"

# Set default admin credentials for demo
export LISTMONK_ADMIN_USER="${ADMIN_USER:-admin}"
export LISTMONK_ADMIN_PASSWORD="${ADMIN_PASSWORD:-admin123}"

echo "==> Running database migrations and install..."
# Install creates the database schema and default admin user
./listmonk --install --idempotent --yes --config=""

echo "==> Starting Listmonk server..."
exec ./listmonk --config=""
