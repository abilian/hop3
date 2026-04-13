#!/bin/bash
set -e

# Validate required environment variables (injected by Hop3)
: "${MYSQL_HOST:?ERROR: MYSQL_HOST is required}"
: "${MYSQL_PORT:?ERROR: MYSQL_PORT is required}"
: "${MYSQL_DATABASE:?ERROR: MYSQL_DATABASE is required}"
: "${MYSQL_USER:?ERROR: MYSQL_USER is required}"
: "${MYSQL_PASSWORD:?ERROR: MYSQL_PASSWORD is required}"

# Wait for MySQL to be ready
echo "Waiting for MySQL at ${MYSQL_HOST}:${MYSQL_PORT}..."
for i in $(seq 1 60); do
    if php -r "new PDO('mysql:host=${MYSQL_HOST};port=${MYSQL_PORT};dbname=${MYSQL_DATABASE}', '${MYSQL_USER}', '${MYSQL_PASSWORD}');" 2>/dev/null; then
        echo "MySQL is ready."
        break
    fi
    if [ "$i" -eq 60 ]; then
        echo "WARNING: MySQL not ready after 120s, starting Apache anyway."
    fi
    sleep 2
done

# Surface PHP errors in Apache's output so the test can see the real
# cause on 500 (instead of WordPress's generic wp-die() page).
cat > /etc/apache2/conf-available/php-errors.conf << 'APACHE_CONF'
<IfModule mod_php.c>
    php_admin_flag log_errors On
    php_admin_flag display_errors On
    php_admin_value error_log /proc/self/fd/2
</IfModule>
APACHE_CONF
a2enconf php-errors >/dev/null 2>&1 || true

# Start Apache
exec apache2ctl -D FOREGROUND
