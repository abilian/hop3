#!/bin/bash
set -e
cat > config/config.ini.php << EOF
[database]
host = "${MYSQL_HOST:-localhost}"
username = "${MYSQL_USER:-matomo}"
password = "${MYSQL_PASSWORD:-}"
dbname = "${MYSQL_DATABASE:-matomo}"
tables_prefix = "matomo_"
charset = "utf8mb4"

[General]
trusted_hosts[] = "localhost"
trusted_hosts[] = "${APP_HOST:-localhost}"
salt = "$(head -c 32 /dev/urandom | base64)"
EOF
echo "Matomo configuration created"
