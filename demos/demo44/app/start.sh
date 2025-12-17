#!/bin/sh
# Startup script for Redmine with PostgreSQL configuration
# Note: Using /bin/sh for Alpine compatibility

set -e

# Unset DATABASE_URL to prevent it from interfering with Redmine's config
unset DATABASE_URL

# Generate database.yml with postgresql adapter
if [ -n "$PGHOST" ]; then
    cat > /usr/src/redmine/config/database.yml <<EOF
production:
  adapter: postgresql
  database: ${PGDATABASE:-redmine}
  host: ${PGHOST}
  port: ${PGPORT:-5432}
  username: ${PGUSER:-redmine}
  password: "${PGPASSWORD}"
  encoding: utf8
EOF
    echo "Generated database.yml with postgresql adapter"
    cat /usr/src/redmine/config/database.yml
fi

# Also set REDMINE_DB_* variables for any other entrypoint logic
if [ -n "$PGHOST" ]; then
    export REDMINE_DB_POSTGRES="$PGHOST"
fi
if [ -n "$PGPORT" ]; then
    export REDMINE_DB_PORT="$PGPORT"
fi
if [ -n "$PGDATABASE" ]; then
    export REDMINE_DB_DATABASE="$PGDATABASE"
fi
if [ -n "$PGUSER" ]; then
    export REDMINE_DB_USERNAME="$PGUSER"
fi
if [ -n "$PGPASSWORD" ]; then
    export REDMINE_DB_PASSWORD="$PGPASSWORD"
fi

# Call the original entrypoint
exec /docker-entrypoint.sh "$@"
