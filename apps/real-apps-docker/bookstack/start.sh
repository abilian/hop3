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

# Generate APP_KEY if not set (Laravel needs exactly 32 bytes, base64-encoded)
if [ -z "${APP_KEY}" ]; then
    APP_KEY="base64:$(head -c 32 /dev/urandom | base64 -w 0)"
fi

# Generate .env file
cat > /var/www/html/.env << EOF
APP_KEY=${APP_KEY}
APP_URL=${APP_URL}
APP_DEBUG=${APP_DEBUG}

DB_HOST=${MYSQL_HOST}
DB_PORT=${MYSQL_PORT}
DB_DATABASE=${MYSQL_DATABASE}
DB_USERNAME=${MYSQL_USER}
DB_PASSWORD=${MYSQL_PASSWORD}

CACHE_DRIVER=file
SESSION_DRIVER=file
QUEUE_CONNECTION=sync
EOF

cd /var/www/html

# Wait for MySQL to be ready
echo "Waiting for MySQL at ${MYSQL_HOST}:${MYSQL_PORT}..."
for i in $(seq 1 30); do
    if php -r "new PDO('mysql:host=${MYSQL_HOST};port=${MYSQL_PORT};dbname=${MYSQL_DATABASE}', '${MYSQL_USER}', '${MYSQL_PASSWORD}');" 2>/dev/null; then
        echo "MySQL is ready."
        break
    fi
    if [ "$i" -eq 30 ]; then
        echo "WARNING: MySQL not ready after 30 attempts, starting Apache anyway."
    fi
    sleep 2
done

# Run migrations (non-fatal so Apache can still serve /status)
if ! php artisan migrate --force 2>&1; then
    echo "WARNING: Migration failed, starting Apache anyway."
fi

# Start Apache
exec apache2ctl -D FOREGROUND
