#!/bin/bash
set -e

# Validate required environment variables (injected by Hop3)
: "${MYSQL_HOST:?ERROR: MYSQL_HOST is required}"
: "${MYSQL_PORT:?ERROR: MYSQL_PORT is required}"
: "${MYSQL_DATABASE:?ERROR: MYSQL_DATABASE is required}"
: "${MYSQL_USER:?ERROR: MYSQL_USER is required}"
: "${MYSQL_PASSWORD:?ERROR: MYSQL_PASSWORD is required}"

# Optional with defaults
APP_URL="${APP_URL:-localhost}"

cd /var/www/html

# Wait for MySQL to be ready
echo "Waiting for MySQL at ${MYSQL_HOST}:${MYSQL_PORT}..."
for i in $(seq 1 30); do
    if php -r "new PDO('mysql:host=${MYSQL_HOST};port=${MYSQL_PORT};dbname=${MYSQL_DATABASE}', '${MYSQL_USER}', '${MYSQL_PASSWORD}');" 2>/dev/null; then
        echo "MySQL is ready."
        break
    fi
    if [ "$i" -eq 30 ]; then
        echo "WARNING: MySQL not ready after 30 attempts."
    fi
    sleep 2
done

# Do NOT pre-create config/config.ini.php. Matomo's own installer
# writes it once the user completes the web-based install flow at
# /index.php?module=Installation. Any hand-crafted config with a
# partial [General] section causes a 500 on bootstrap because Matomo
# validates the config as fully-defined (no missing keys, plugin list
# consistent). Let the installer do its job.
#
# The [database] section will be written by Matomo using MYSQL_*
# values we expose as env vars — but it needs them in the form that
# its install wizard reads at runtime (config/env.global.php or
# a simple pre-fill of the DB form). For now: let the user go
# through the web wizard.

# Ensure directories are writable by www-data
chown -R www-data:www-data tmp config
chmod -R ug+rwX tmp config

# Start Apache
exec apache2ctl -D FOREGROUND
