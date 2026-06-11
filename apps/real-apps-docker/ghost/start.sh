#!/bin/bash
# Startup script for Ghost with MySQL configuration

set -e

echo "==> Starting Ghost"

cd /var/lib/ghost

# Parse DATABASE_URL if provided
if [ -n "$DATABASE_URL" ]; then
    # Extract components from mysql://user:pass@host:port/database
    DB_USER=$(echo "$DATABASE_URL" | sed -n 's|.*://\([^:]*\):.*|\1|p')
    DB_PASSWORD=$(echo "$DATABASE_URL" | sed -n 's|.*://[^:]*:\([^@]*\)@.*|\1|p')
    DB_HOST=$(echo "$DATABASE_URL" | sed -n 's|.*@\([^:/]*\).*|\1|p')
    DB_PORT=$(echo "$DATABASE_URL" | sed -n 's|.*:\([0-9]*\)/.*|\1|p')
    DB_NAME=$(echo "$DATABASE_URL" | sed -n 's|.*/\([^?]*\).*|\1|p')

    # Default port if not specified
    DB_PORT=${DB_PORT:-3306}

    echo "==> Database config:"
    echo "    Host: $DB_HOST"
    echo "    Port: $DB_PORT"
    echo "    User: $DB_USER"
    echo "    Database: $DB_NAME"

    # Export for Ghost (uses nested config format)
    export database__client="mysql"
    export database__connection__host="$DB_HOST"
    export database__connection__port="$DB_PORT"
    export database__connection__user="$DB_USER"
    export database__connection__password="$DB_PASSWORD"
    export database__connection__database="$DB_NAME"
else
    echo "==> Using SQLite database (no DATABASE_URL provided)"
    export database__client="sqlite3"
    export database__connection__filename="/var/lib/ghost/content/data/ghost.db"
fi

# Set site URL from HOST_NAME if provided
if [ -n "$HOST_NAME" ]; then
    export url="https://${HOST_NAME}"
    echo "==> Site URL: $url"
else
    export url="http://localhost:2368"
fi

# Ghost needs to listen on all interfaces
export server__host="0.0.0.0"
export server__port="2368"

echo "==> Starting Ghost server..."

# Run as ghost user
exec su -s /bin/bash ghost -c "cd /var/lib/ghost && node current/index.js"
