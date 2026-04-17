#!/bin/bash
set -e

: "${PORT:?ERROR: PORT is required}"
: "${PGHOST:?ERROR: PGHOST is required}"

cd /var/www/mediawiki

if [ ! -f LocalSettings.php ]; then
    ADMIN_PASS="${MW_ADMIN_PASS:-$(head -c 16 /dev/urandom | base64 | tr -d '+/=' | head -c 20)}"

    php maintenance/install.php \
        --dbtype=postgres \
        --dbserver="${PGHOST}" \
        --dbport="${PGPORT:-5432}" \
        --dbname="${PGDATABASE}" \
        --dbuser="${PGUSER}" \
        --dbpass="${PGPASSWORD}" \
        --installdbuser="${PGUSER}" \
        --installdbpass="${PGPASSWORD}" \
        --server="http://localhost" \
        --scriptpath="" \
        --lang="${MW_LANG:-en}" \
        --pass="${ADMIN_PASS}" \
        "${MW_SITENAME:-Hop3 MediaWiki}" \
        "${MW_ADMIN_USER:-admin}"

    echo "MediaWiki installed. Admin password: ${ADMIN_PASS}"
else
    php maintenance/update.php --quick
fi

exec php -S "0.0.0.0:${PORT}"
