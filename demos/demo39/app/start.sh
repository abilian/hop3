#!/bin/bash
# Startup script for Matomo with MySQL configuration

set -e

# Map MYSQL_* variables (from Hop3 addon) to MATOMO_DATABASE_* variables
if [ -n "$MYSQL_HOST" ]; then
    # Matomo expects host:port format
    export MATOMO_DATABASE_HOST="${MYSQL_HOST}:${MYSQL_PORT:-3306}"
fi
if [ -n "$MYSQL_USER" ]; then
    export MATOMO_DATABASE_USERNAME="$MYSQL_USER"
fi
if [ -n "$MYSQL_PASSWORD" ]; then
    export MATOMO_DATABASE_PASSWORD="$MYSQL_PASSWORD"
fi
if [ -n "$MYSQL_DATABASE" ]; then
    export MATOMO_DATABASE_DBNAME="$MYSQL_DATABASE"
fi
export MATOMO_DATABASE_ADAPTER="mysql"

# Call the original entrypoint with apache
exec /entrypoint.sh "$@"
