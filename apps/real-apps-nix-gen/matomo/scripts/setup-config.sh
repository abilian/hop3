#!/bin/bash
set -e
cd "$(dirname "$0")/.."

# Configure and install Matomo headlessly.
#
# Two things this must NOT do, both of which the previous version did:
#
#  1. Rewrite config.ini.php on every deploy. Matomo OWNS that file — the
#     installer and the admin UI write settings into it — so regenerating it
#     discarded everything Matomo (and the operator) had configured, including
#     the record that it was ever installed. It is seeded once, then left alone.
#  2. Mint a fresh `salt` each deploy. The salt keys Matomo's hashing; rotating
#     it invalidates sessions and breaks stored values. It is now a stable
#     generated secret (ADR 046), injected unchanged on every deploy.

: "${MYSQL_DATABASE:?the mysql addon did not provision MYSQL_DATABASE}"
: "${MATOMO_SALT:?MATOMO_SALT must be a stable generated [env] secret (ADR 046)}"

mkdir -p config tmp/assets tmp/cache tmp/logs tmp/tcpdf tmp/templates_c

# trusted_hosts must list the host Matomo is actually served on, or it rejects
# the request as a host-header attack. HOST_NAME is the platform's own value;
# the old config used ${APP_HOST}, which Hop3 never sets.
host="${HOST_NAME:-localhost}"

if [ -f config/config.ini.php ]; then
    echo "Matomo: keeping the existing config.ini.php (Matomo manages it)"
else
    cat > config/config.ini.php << EOF
[database]
host = "${MYSQL_HOST:-127.0.0.1}"
port = "${MYSQL_PORT:-3306}"
username = "${MYSQL_USER}"
password = "${MYSQL_PASSWORD}"
dbname = "${MYSQL_DATABASE}"
tables_prefix = "matomo_"
charset = "utf8mb4"

[General]
salt = "${MATOMO_SALT}"
trusted_hosts[] = "localhost"
trusted_hosts[] = "${host}"
EOF
    chmod 600 config/config.ini.php
    echo "Matomo: seeded config.ini.php"
fi

# Install (schema + superuser + first site). install.php is idempotent on its
# own — it returns early when tables already exist — and fails loud otherwise,
# rather than leaving a running app nobody can log into.
: "${HOP3_ADMIN_USER:?ADR-056 admin bootstrap requires HOP3_ADMIN_USER}"
: "${HOP3_ADMIN_PASSWORD:?ADR-056 admin bootstrap requires HOP3_ADMIN_PASSWORD}"
: "${HOP3_ADMIN_EMAIL:?ADR-056 admin bootstrap requires HOP3_ADMIN_EMAIL}"

php scripts/install.php

# Bring the database in line with the files. Required after a version bump (a
# redeploy with a newer Matomo), and on a fresh install it stops the app landing
# on the "database upgrade required" screen instead of the sign-in page.
# Idempotent: prints "Everything is already up to date" when there is nothing to do.
php console core:update --yes

echo "Matomo configuration ready"
