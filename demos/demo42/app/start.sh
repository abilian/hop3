#!/bin/bash
# Startup script for LimeSurvey with MySQL configuration

set -e

# Map MYSQL_* variables (from Hop3 addon) to DB_* variables (expected by LimeSurvey)
if [ -n "$MYSQL_HOST" ]; then
    export DB_HOST="$MYSQL_HOST"
fi
if [ -n "$MYSQL_PORT" ]; then
    export DB_PORT="$MYSQL_PORT"
fi
if [ -n "$MYSQL_DATABASE" ]; then
    export DB_NAME="$MYSQL_DATABASE"
fi
if [ -n "$MYSQL_USER" ]; then
    export DB_USERNAME="$MYSQL_USER"
fi
if [ -n "$MYSQL_PASSWORD" ]; then
    export DB_PASSWORD="$MYSQL_PASSWORD"
fi
export DB_TYPE="mysql"

# Set default admin credentials if not provided
export ADMIN_USER=${ADMIN_USER:-admin}
export ADMIN_PASSWORD=${ADMIN_PASSWORD:-admin}
export ADMIN_NAME=${ADMIN_NAME:-"Admin User"}
export ADMIN_EMAIL=${ADMIN_EMAIL:-"admin@example.com"}

# Start the original entrypoint with CMD
exec /usr/local/bin/entrypoint.sh "$@"
