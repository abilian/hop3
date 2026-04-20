#!/bin/bash
set -e

: "${PORT:?ERROR: PORT is required}"
: "${PGHOST:?ERROR: PGHOST is required}"
: "${PGPORT:?ERROR: PGPORT is required}"
: "${PGDATABASE:?ERROR: PGDATABASE is required}"
: "${PGUSER:?ERROR: PGUSER is required}"
: "${PGPASSWORD:?ERROR: PGPASSWORD is required}"

# Keycloak reads KC_* env vars natively; build the JDBC URL from the
# PG* vars the Hop3 postgres addon injects.
export KC_DB=postgres
export KC_DB_URL="jdbc:postgresql://${PGHOST}:${PGPORT}/${PGDATABASE}"
export KC_DB_USERNAME="${PGUSER}"
export KC_DB_PASSWORD="${PGPASSWORD}"

# Bootstrap admin on first start. Changes after first boot are ignored.
export KC_BOOTSTRAP_ADMIN_USERNAME="${KC_BOOTSTRAP_ADMIN_USERNAME:-admin}"
export KC_BOOTSTRAP_ADMIN_PASSWORD="${KC_BOOTSTRAP_ADMIN_PASSWORD:-changeme}"

# start-dev: HTTP only, no hostname requirement, auto-build. Good for
# a first-pass variant; production (v0.6+) would use `start` behind
# nginx with proper hostname + TLS config.
exec /opt/keycloak/bin/kc.sh start-dev \
    --http-host=0.0.0.0 \
    --http-port="${PORT}"
