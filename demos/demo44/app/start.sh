#!/bin/sh
# Startup script for Redmine with MySQL configuration
# Note: Using /bin/sh for Alpine compatibility

set -e

# Unset DATABASE_URL to prevent it from interfering with Redmine's config
unset DATABASE_URL

# Disable MySQL SSL via environment variable (recognized by mysql2 gem)
export MYSQL_SSL_MODE=DISABLED

# Generate database.yml directly with mysql2 adapter
if [ -n "$MYSQL_HOST" ]; then
    cat > /usr/src/redmine/config/database.yml <<EOF
production:
  adapter: mysql2
  database: ${MYSQL_DATABASE:-redmine}
  host: ${MYSQL_HOST}
  port: ${MYSQL_PORT:-3306}
  username: ${MYSQL_USER:-redmine}
  password: "${MYSQL_PASSWORD}"
  encoding: utf8mb4
EOF
    echo "Generated database.yml with mysql2 adapter"
    cat /usr/src/redmine/config/database.yml
fi

# Also set REDMINE_DB_* variables for any other entrypoint logic
if [ -n "$MYSQL_HOST" ]; then
    export REDMINE_DB_MYSQL="$MYSQL_HOST"
fi
if [ -n "$MYSQL_PORT" ]; then
    export REDMINE_DB_PORT="$MYSQL_PORT"
fi
if [ -n "$MYSQL_DATABASE" ]; then
    export REDMINE_DB_DATABASE="$MYSQL_DATABASE"
fi
if [ -n "$MYSQL_USER" ]; then
    export REDMINE_DB_USERNAME="$MYSQL_USER"
fi
if [ -n "$MYSQL_PASSWORD" ]; then
    export REDMINE_DB_PASSWORD="$MYSQL_PASSWORD"
fi

# Call the original entrypoint
exec /docker-entrypoint.sh "$@"
