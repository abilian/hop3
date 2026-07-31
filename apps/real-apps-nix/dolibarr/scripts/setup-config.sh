#!/bin/bash
set -e
cd "$(dirname "$0")/.."

# Install Dolibarr headlessly.
#
# Dolibarr ships no installer CLI, only a browser wizard — which is why this app
# previously deployed to a running-but-uninstalled state: it wrote conf.php and
# stopped, leaving no schema, no admin, and nothing to log into. But each wizard
# step also reads its inputs from $argv when run under the PHP CLI (see the
# GETPOST(...) ?: $argv[n] pattern at the top of htdocs/install/stepN.php), so
# the same steps the browser drives can be driven from here.
#
# The flow mirrors the wizard: conf.php -> step1 (create schema) -> step2
# (reference data + keys) -> step5 (create the super-admin, then lock the
# installer). install.forced.php pins the answers so a visit to the installer
# cannot re-run it with different ones.

APP_DIR="$(pwd)"
DOC_ROOT="${APP_DIR}/documents"
PUBLIC_URL="${HOP3_PUBLIC_URL:-http://localhost:${PORT:-8080}}"

mkdir -p "$DOC_ROOT" htdocs/conf

# The documents dir holds uploads and generated PDFs; it must not be world-readable.
chmod 700 "$DOC_ROOT"

# conf.php is written every deploy so the DB credentials and public URL follow
# the platform (the addon may rotate them; the URL changes when a domain is
# attached). The install steps below read it back.
cat > htdocs/conf/conf.php << EOF
<?php
\$dolibarr_main_url_root='${PUBLIC_URL}';
\$dolibarr_main_document_root='${APP_DIR}/htdocs';
\$dolibarr_main_data_root='${DOC_ROOT}';
\$dolibarr_main_db_host='${PGHOST:-127.0.0.1}';
\$dolibarr_main_db_port='${PGPORT:-5432}';
\$dolibarr_main_db_name='${PGDATABASE:?PGDATABASE not set - the postgres addon did not provision}';
\$dolibarr_main_db_user='${PGUSER:?PGUSER not set}';
\$dolibarr_main_db_pass='${PGPASSWORD:?PGPASSWORD not set}';
\$dolibarr_main_db_type='pgsql';
\$dolibarr_main_db_character_set='UTF8';
\$dolibarr_main_db_collation='C';
\$dolibarr_main_authentication='dolibarr';
\$dolibarr_main_prod='1';
EOF
chmod 600 htdocs/conf/conf.php

# step5 writes documents/install.lock, which lives on the persistent volume — so
# this is the idempotence gate: a redeploy rewrites conf.php and stops here.
if [ -f "${DOC_ROOT}/install.lock" ]; then
    echo "Dolibarr already installed (install.lock present); skipping installer"
    exit 0
fi

: "${HOP3_ADMIN_USER:?ADR-056 admin bootstrap requires HOP3_ADMIN_USER}"
: "${HOP3_ADMIN_PASSWORD:?ADR-056 admin bootstrap requires HOP3_ADMIN_PASSWORD}"

# Pin every wizard answer. noedit=2 locks all set variables, so even if the
# installer is reachable before it is locked it cannot be driven with different
# ones. Hop3's addon already created the database and its user, so the installer
# must not try to create either.
cat > htdocs/install/install.forced.php << EOF
<?php
\$force_install_noedit = 2;
\$force_install_nophpinfo = true;
\$force_install_message = 'Installed by Hop3';
\$force_install_main_data_root = '${DOC_ROOT}';
\$force_install_mainforcehttps = false;
\$force_install_type = 'pgsql';
\$force_install_dbserver = '${PGHOST:-127.0.0.1}';
\$force_install_port = ${PGPORT:-5432};
\$force_install_database = '${PGDATABASE}';
\$force_install_databaselogin = '${PGUSER}';
\$force_install_databasepass = '${PGPASSWORD}';
\$force_install_prefix = 'llx_';
\$force_install_createdatabase = false;
\$force_install_createuser = false;
\$force_install_dolibarrlogin = '${HOP3_ADMIN_USER}';
\$force_install_lockinstall = true;
EOF

cd htdocs/install

# argv order is positional, taken from the GETPOST(...) ?: $argv[n] lines at the
# top of each step. The db root user/password are empty: the database and its
# owner already exist, so the installer connects as that owner.
echo "Dolibarr: creating the schema (step1)..."
php step1.php set auto "${APP_DIR}/htdocs" "${DOC_ROOT}" "${PUBLIC_URL}" \
    "" "" pgsql "${PGHOST:-127.0.0.1}" "${PGDATABASE}" "${PGUSER}" \
    "${PGPASSWORD}" "${PGPORT:-5432}" llx_ 0 0 > /tmp/dolibarr-step1.out 2>&1 || {
    echo "Dolibarr step1 (schema) failed:" >&2; tail -20 /tmp/dolibarr-step1.out >&2; exit 1
}

echo "Dolibarr: loading reference data (step2)..."
php step2.php set auto > /tmp/dolibarr-step2.out 2>&1 || {
    echo "Dolibarr step2 (reference data) failed:" >&2; tail -20 /tmp/dolibarr-step2.out >&2; exit 1
}

echo "Dolibarr: creating the super-administrator (step5)..."
php step5.php 0.0.0 "${DOLIBARR_VERSION:-19.0.0}" auto set \
    "${HOP3_ADMIN_USER}" "${HOP3_ADMIN_PASSWORD}" "${HOP3_ADMIN_PASSWORD}" 1 \
    > /tmp/dolibarr-step5.out 2>&1 || {
    echo "Dolibarr step5 (admin) failed:" >&2; tail -20 /tmp/dolibarr-step5.out >&2; exit 1
}

cd "$APP_DIR"

# Verify the EFFECT, not the exit codes: these steps are web pages run under the
# CLI and can print an error while still exiting 0. The install is only real if
# the admin row exists.
admin_count=$(PGPASSWORD="${PGPASSWORD}" psql -h "${PGHOST:-127.0.0.1}" \
    -p "${PGPORT:-5432}" -U "${PGUSER}" -d "${PGDATABASE}" -tAc \
    "SELECT COUNT(*) FROM llx_user WHERE login = '${HOP3_ADMIN_USER}'" 2>/dev/null || echo "error")

if [ "$admin_count" = "error" ]; then
    echo "Dolibarr install can't verify itself: querying llx_user failed" >&2
    exit 1
fi
if [ "$admin_count" -lt 1 ]; then
    echo "Dolibarr install did not create the '${HOP3_ADMIN_USER}' account -- refusing to report success" >&2
    tail -20 /tmp/dolibarr-step5.out >&2
    exit 1
fi

# step5 writes install.lock when passed installlock=1; create it ourselves if it
# somehow did not. An unlocked installer on a reachable app is a takeover path —
# anyone could re-run it and set their own admin password.
if [ ! -f "${DOC_ROOT}/install.lock" ]; then
    echo "Dolibarr: installer did not self-lock; locking it now" >&2
    : > "${DOC_ROOT}/install.lock"
fi

echo "Dolibarr installed; admin '${HOP3_ADMIN_USER}' created"
