#!/bin/bash
# Startup script for Redmine with PostgreSQL configuration

set -e

echo "==> Starting Redmine"

cd /usr/src/redmine

# Unset DATABASE_URL to prevent it from interfering with Redmine's config
unset DATABASE_URL

# Generate database.yml with postgresql adapter
if [ -n "$PGHOST" ]; then
    echo "==> Creating database.yml"
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

    echo "==> Database config:"
    echo "    Host: ${PGHOST}"
    echo "    Port: ${PGPORT:-5432}"
    echo "    User: ${PGUSER}"
    echo "    Database: ${PGDATABASE:-redmine}"
fi

# Generate secret token if not present
if [ ! -f /usr/src/redmine/config/initializers/secret_token.rb ]; then
    echo "==> Generating secret token"
    bundle exec rake generate_secret_token
fi

# Run database migrations
if [ -n "$PGHOST" ]; then
    echo "==> Running database migrations"
    bundle exec rake db:migrate || true
fi

echo "==> Starting Rails server..."
exec bundle exec rails server -b 0.0.0.0 -p 3000
