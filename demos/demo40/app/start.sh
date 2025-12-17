#!/bin/bash
# Startup script for Ghost with MySQL configuration

set -e

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

    # Export for Ghost (uses nested config format)
    export database__client="mysql"
    export database__connection__host="$DB_HOST"
    export database__connection__port="$DB_PORT"
    export database__connection__user="$DB_USER"
    export database__connection__password="$DB_PASSWORD"
    export database__connection__database="$DB_NAME"
fi

# Set site URL from HOST_NAME if provided
if [ -n "$HOST_NAME" ]; then
    export url="https://${HOST_NAME}"
fi

# Start Ghost
exec docker-entrypoint.sh node current/index.js
