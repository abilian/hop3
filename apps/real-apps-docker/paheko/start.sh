#!/bin/bash
set -e

: "${PORT:?ERROR: PORT is required}"

# Paheko listens on Apache's port; map the Hop3-assigned PORT to
# Apache's Listen directive.
sed -i "s/Listen 80/Listen ${PORT}/" /etc/apache2/ports.conf
sed -i "s/\\*:80/*:${PORT}/" /etc/apache2/sites-available/000-default.conf

# Paheko's default data location is DATA_ROOT; seed a config if the
# operator hasn't supplied one.
if [ ! -f /var/www/paheko/src/config.local.php ]; then
    cat > /var/www/paheko/src/config.local.php <<EOF
<?php
const DATA_ROOT = '/data';
const DB_FILE = DATA_ROOT . '/paheko.sqlite';
const SECRET_KEY = '$(head -c 32 /dev/urandom | base64)';
EOF
    chown www-data:www-data /var/www/paheko/src/config.local.php
fi

exec apache2ctl -D FOREGROUND
