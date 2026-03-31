#!/bin/bash
set -e
cd "$(dirname "$0")/.."

# Create config if not exists
if [ ! -f config.php ]; then
    cp config-sample.php config.php
    sed -i "s|BASE_URL.*|BASE_URL = '${APP_URL:-http://localhost:8080}';|" config.php
    sed -i "s|DB_HOST.*|DB_HOST = '${MYSQL_HOST:-localhost}';|" config.php
    sed -i "s|DB_NAME.*|DB_NAME = '${MYSQL_DATABASE:-easyappointments}';|" config.php
    sed -i "s|DB_USERNAME.*|DB_USERNAME = '${MYSQL_USER:-easyappointments}';|" config.php
    sed -i "s|DB_PASSWORD.*|DB_PASSWORD = '${MYSQL_PASSWORD:-}';|" config.php
fi

echo "Easy!Appointments configuration ready"
