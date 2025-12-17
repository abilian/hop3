#!/bin/bash
# Startup script for EasyAppointments with MySQL configuration

set -e

# Map MYSQL_* variables (from Hop3 addon) to DB_* variables (expected by EasyAppointments)
if [ -n "$MYSQL_HOST" ]; then
    export DB_HOST="$MYSQL_HOST"
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

# Set base URL from HOST_NAME if provided
if [ -n "$HOST_NAME" ]; then
    export BASE_URL="https://${HOST_NAME}"
fi

# Call the original entrypoint (docker-entrypoint.sh handles config.php creation)
exec docker-entrypoint.sh
