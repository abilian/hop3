#!/bin/bash
set -e

: "${PGHOST:?ERROR: PGHOST is required}"

# MediaWiki's maintenance/install.php generates LocalSettings.php.
# Only run it on the first deploy; subsequent redeploys keep the
# existing config (which may carry operator overrides).
if [ ! -f LocalSettings.php ]; then
    echo "Running MediaWiki first-install..."
    # Seed admin password if unset so the install completes non-
    # interactively; operator rotates via Special:PasswordReset.
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
    echo "Change it via Special:ChangePassword on first login."
else
    echo "LocalSettings.php already present — running update.php"
    php maintenance/update.php --quick
fi
