#!/bin/bash
set -e

# Validate required environment variables (injected by Hop3)
: "${MYSQL_HOST:?ERROR: MYSQL_HOST is required}"
: "${MYSQL_PORT:?ERROR: MYSQL_PORT is required}"
: "${MYSQL_DATABASE:?ERROR: MYSQL_DATABASE is required}"
: "${MYSQL_USER:?ERROR: MYSQL_USER is required}"
: "${MYSQL_PASSWORD:?ERROR: MYSQL_PASSWORD is required}"

# Optional with defaults
APP_DEBUG="${APP_DEBUG:-false}"
APP_URL="${APP_URL:-http://localhost:8080}"

cd /var/www/html

# Wait for MySQL to be ready before proceeding
echo "Waiting for MySQL at ${MYSQL_HOST}:${MYSQL_PORT}..."
for i in $(seq 1 30); do
    if mysqladmin ping -h"${MYSQL_HOST}" -P"${MYSQL_PORT}" -u"${MYSQL_USER}" -p"${MYSQL_PASSWORD}" --silent 2>/dev/null; then
        echo "MySQL is ready."
        break
    fi
    if [ "$i" -eq 30 ]; then
        echo "ERROR: MySQL did not become ready within 60 seconds."
        exit 1
    fi
    echo "MySQL not ready (attempt $i/30), waiting..."
    sleep 2
done

# Generate .env file
cat > .env << EOF
APP_NAME="Invoice Ninja"
APP_KEY=${APP_KEY:-base64:$(head -c 32 /dev/urandom | base64 -w 0)}
APP_URL=${APP_URL}
APP_DEBUG=${APP_DEBUG}
APP_ENV=production

DB_CONNECTION=mysql
DB_HOST=${MYSQL_HOST}
DB_PORT=${MYSQL_PORT}
DB_DATABASE=${MYSQL_DATABASE}
DB_USERNAME=${MYSQL_USER}
DB_PASSWORD=${MYSQL_PASSWORD}

CACHE_DRIVER=file
SESSION_DRIVER=file
QUEUE_CONNECTION=sync

MAIL_MAILER=log

NINJA_ENVIRONMENT=selfhost
TRUSTED_PROXIES=*
EOF

chown www-data:www-data .env

# Ensure storage directories exist and are writable
mkdir -p storage/framework/{sessions,views,cache}
mkdir -p storage/logs
mkdir -p bootstrap/cache
chown -R www-data:www-data storage bootstrap/cache
chmod -R 775 storage bootstrap/cache

# Create storage link if not exists
if [ ! -L public/storage ]; then
    php artisan storage:link
fi

# Clear and cache config (non-fatal)
php artisan config:clear 2>/dev/null || true
php artisan cache:clear 2>/dev/null || true

# Run migrations (non-fatal so Apache can still start)
if ! php artisan migrate --force 2>&1; then
    echo "WARNING: Migration failed, starting Apache anyway."
fi

# Start Apache
exec apache2ctl -D FOREGROUND
