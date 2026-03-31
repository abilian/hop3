#!/bin/bash
set -e

# Monica requires an APP_KEY to run. Generate it first.
# We need a minimal .env first for artisan to work
if [ ! -f .env ]; then
    # Create minimal .env for key generation
    echo "APP_KEY=" > .env
fi

# Generate a proper Laravel key
APP_KEY=$(php artisan key:generate --show 2>/dev/null || echo "base64:$(head -c 32 /dev/urandom | base64)")

# Now create the full .env
cat > .env << EOF
APP_KEY=${APP_KEY}
APP_URL=${APP_URL:-http://localhost:${PORT:-8080}}
APP_ENV=production
APP_DEBUG=false

DB_CONNECTION=mysql
DB_HOST=${MYSQL_HOST:-localhost}
DB_PORT=${MYSQL_PORT:-3306}
DB_DATABASE=${MYSQL_DATABASE:-monica}
DB_USERNAME=${MYSQL_USER:-monica}
DB_PASSWORD=${MYSQL_PASSWORD:-}

HASH_SALT=$(head -c 20 /dev/urandom | base64)
HASH_LENGTH=18

# Disable features that need additional setup
MAIL_MAILER=log
QUEUE_CONNECTION=sync
EOF

# Run migrations
echo "Running database migrations..."
php artisan migrate --force

# Note: We deliberately skip config:cache/route:cache/view:cache
# because php artisan serve has a file watcher that detects these
# changes and triggers restarts, causing 503 errors during startup.

echo "Monica configuration completed"
