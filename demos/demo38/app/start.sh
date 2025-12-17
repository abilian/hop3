#!/bin/bash
# Startup script for BookStack with MySQL configuration

set -e

cd /var/www/html

# Parse DATABASE_URL if provided
if [ -n "$DATABASE_URL" ]; then
    # Extract components from mysql://user:pass@host:port/database
    export DB_CONNECTION="mysql"
    export DB_USERNAME=$(echo "$DATABASE_URL" | sed -n 's|.*://\([^:]*\):.*|\1|p')
    export DB_PASSWORD=$(echo "$DATABASE_URL" | sed -n 's|.*://[^:]*:\([^@]*\)@.*|\1|p')
    export DB_HOST=$(echo "$DATABASE_URL" | sed -n 's|.*@\([^:/]*\).*|\1|p')
    export DB_PORT=$(echo "$DATABASE_URL" | sed -n 's|.*:\([0-9]*\)/.*|\1|p')
    export DB_DATABASE=$(echo "$DATABASE_URL" | sed -n 's|.*/\([^?]*\).*|\1|p')

    # Default port if not specified
    DB_PORT=${DB_PORT:-3306}
fi

# Set APP_URL from HOST_NAME
if [ -n "$HOST_NAME" ]; then
    export APP_URL="https://${HOST_NAME}"
fi

# Generate APP_KEY if not set
if [ -z "$APP_KEY" ]; then
    export APP_KEY=$(php artisan key:generate --show 2>/dev/null || echo "base64:$(openssl rand -base64 32)")
fi

# Create .env file
cat > .env << EOF
APP_ENV=${APP_ENV:-production}
APP_DEBUG=${APP_DEBUG:-false}
APP_KEY=${APP_KEY}
APP_URL=${APP_URL:-http://localhost}

DB_CONNECTION=${DB_CONNECTION:-mysql}
DB_HOST=${DB_HOST:-localhost}
DB_PORT=${DB_PORT:-3306}
DB_DATABASE=${DB_DATABASE:-bookstack}
DB_USERNAME=${DB_USERNAME:-root}
DB_PASSWORD=${DB_PASSWORD:-}

MAIL_DRIVER=log
EOF

# Run migrations
php artisan migrate --force 2>/dev/null || true

# Clear and cache config
php artisan config:clear
php artisan cache:clear

# Start Apache
exec apache2-foreground
