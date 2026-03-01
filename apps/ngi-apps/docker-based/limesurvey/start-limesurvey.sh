#!/bin/bash
set -e

# Validate required environment variables (injected by Hop3)
: "${PGHOST:?ERROR: PGHOST is required}"
: "${PGPORT:?ERROR: PGPORT is required}"
: "${PGDATABASE:?ERROR: PGDATABASE is required}"
: "${PGUSER:?ERROR: PGUSER is required}"
: "${PGPASSWORD:?ERROR: PGPASSWORD is required}"

# Optional with defaults
ADMIN_USER="${ADMIN_USER:-admin}"
ADMIN_NAME="${ADMIN_NAME:-Administrator}"
ADMIN_EMAIL="${ADMIN_EMAIL:-admin@example.com}"
ADMIN_PASSWORD="${ADMIN_PASSWORD:-admin123}"

# Generate config.php
cat > /var/www/limesurvey/application/config/config.php << 'EOF'
<?php
return array(
    'components' => array(
        'db' => array(
            'connectionString' => 'pgsql:host=${PGHOST};port=${PGPORT};dbname=${PGDATABASE};',
            'username' => '${PGUSER}',
            'password' => '${PGPASSWORD}',
            'charset' => 'utf8',
            'tablePrefix' => 'lime_',
        ),
        'urlManager' => array(
            'urlFormat' => 'path',
            'showScriptName' => false,
        ),
    ),
    'config' => array(
        'debug' => 0,
        'debugsql' => 0,
    ),
);
EOF

# Replace environment variables in config
sed -i "s|\${PGHOST}|${PGHOST}|g" /var/www/limesurvey/application/config/config.php
sed -i "s|\${PGPORT}|${PGPORT}|g" /var/www/limesurvey/application/config/config.php
sed -i "s|\${PGDATABASE}|${PGDATABASE}|g" /var/www/limesurvey/application/config/config.php
sed -i "s|\${PGUSER}|${PGUSER}|g" /var/www/limesurvey/application/config/config.php
sed -i "s|\${PGPASSWORD}|${PGPASSWORD}|g" /var/www/limesurvey/application/config/config.php

# Link upload directory to persistent storage
rm -rf /var/www/limesurvey/upload
ln -sf /var/lib/limesurvey/upload /var/www/limesurvey/upload

# Set permissions
chown -R www-data:www-data /var/www/limesurvey /var/lib/limesurvey
chmod -R 755 /var/www/limesurvey/tmp 2>/dev/null || true
chmod -R 755 /var/lib/limesurvey/upload

# Run LimeSurvey CLI installer if database is empty
cd /var/www/limesurvey
php application/commands/console.php install "$ADMIN_USER" "$ADMIN_PASSWORD" "$ADMIN_NAME" "$ADMIN_EMAIL" 2>/dev/null || true

# Start Apache in foreground
exec apache2ctl -D FOREGROUND
