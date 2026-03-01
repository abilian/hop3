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

# Start Apache
exec apache2ctl -D FOREGROUND
