#!/bin/bash
set -e

# Validate required environment variables (injected by Hop3)
: "${MYSQL_HOST:?ERROR: MYSQL_HOST is required}"
: "${MYSQL_PORT:?ERROR: MYSQL_PORT is required}"
: "${MYSQL_DATABASE:?ERROR: MYSQL_DATABASE is required}"
: "${MYSQL_USER:?ERROR: MYSQL_USER is required}"
: "${MYSQL_PASSWORD:?ERROR: MYSQL_PASSWORD is required}"

# Optional with defaults
APP_URL="${APP_URL:-http://localhost:8080}"

cd /var/www/html

# Create config.php
cat > config.php << EOF
<?php
class Config {
    const BASE_URL = "${APP_URL}";
    const LANGUAGE = "english";
    const DEBUG_MODE = false;

    const DB_HOST = "${MYSQL_HOST}";
    const DB_NAME = "${MYSQL_DATABASE}";
    const DB_USERNAME = "${MYSQL_USER}";
    const DB_PASSWORD = "${MYSQL_PASSWORD}";

    const GOOGLE_SYNC_FEATURE = false;
    const GOOGLE_CLIENT_ID = "";
    const GOOGLE_CLIENT_SECRET = "";
}
EOF

chown www-data:www-data config.php

# Ensure storage is writable
chown -R www-data:www-data storage
chmod -R 755 storage

# Wait for MySQL to be ready before starting
echo "Waiting for MySQL at ${MYSQL_HOST}:${MYSQL_PORT}..."
for i in $(seq 1 60); do
    if php -r "
        \$conn = @new mysqli('${MYSQL_HOST}', '${MYSQL_USER}', '${MYSQL_PASSWORD}', '${MYSQL_DATABASE}', ${MYSQL_PORT});
        if (\$conn->connect_error) { exit(1); }
        \$conn->close();
    " 2>/dev/null; then
        echo "MySQL is ready."
        break
    fi
    if [ "$i" -eq 60 ]; then
        echo "WARNING: MySQL not reachable after 120s, starting Apache anyway."
    fi
    sleep 2
done

# Run database installation if tables don't exist yet
# This creates the schema and seeds default data (admin user, default service, etc.)
if ! php -r "
    require 'config.php';
    \$conn = new mysqli(Config::DB_HOST, Config::DB_USERNAME, Config::DB_PASSWORD, Config::DB_NAME, ${MYSQL_PORT});
    \$result = \$conn->query(\"SHOW TABLES LIKE 'ea_users'\");
    exit(\$result && \$result->num_rows > 0 ? 0 : 1);
" 2>/dev/null; then
    echo "Database tables not found, running initial installation..."
    php index.php console install || echo "WARNING: Console install failed, app will show installation wizard"
fi

# Start Apache
exec apache2ctl -D FOREGROUND
