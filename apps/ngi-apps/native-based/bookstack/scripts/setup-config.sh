#!/bin/bash
set -e
cat > .env << EOF
APP_KEY=$(php artisan key:generate --show 2>/dev/null || echo "base64:$(head -c 32 /dev/urandom | base64)")
APP_URL=${APP_URL:-http://localhost:${PORT:-8080}}
APP_ENV=production
APP_DEBUG=false
DB_CONNECTION=mysql
DB_HOST=${MYSQL_HOST:-localhost}
DB_PORT=${MYSQL_PORT:-3306}
DB_DATABASE=${MYSQL_DATABASE:-bookstack}
DB_USERNAME=${MYSQL_USER:-bookstack}
DB_PASSWORD=${MYSQL_PASSWORD:-}
EOF
php artisan migrate --force
echo "BookStack configuration created"
