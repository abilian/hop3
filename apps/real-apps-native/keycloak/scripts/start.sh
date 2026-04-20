#!/bin/bash
set -e

: "${PORT:?ERROR: PORT is required}"
: "${PGHOST:?ERROR: PGHOST is required}"
: "${PGPORT:?ERROR: PGPORT is required}"
: "${PGDATABASE:?ERROR: PGDATABASE is required}"
: "${PGUSER:?ERROR: PGUSER is required}"
: "${PGPASSWORD:?ERROR: PGPASSWORD is required}"

# Point Keycloak's kc.sh at the local JRE 21 we unpacked at build time.
# kc.sh probes JAVA_HOME and JAVA before falling back to system `java`;
# setting both here bypasses any system JDK (which is likely 17).
export JAVA_HOME="$PWD/jre"
export PATH="$JAVA_HOME/bin:$PATH"

export KC_DB=postgres
export KC_DB_URL="jdbc:postgresql://${PGHOST}:${PGPORT}/${PGDATABASE}"
export KC_DB_USERNAME="${PGUSER}"
export KC_DB_PASSWORD="${PGPASSWORD}"
export KC_BOOTSTRAP_ADMIN_USERNAME="${KC_BOOTSTRAP_ADMIN_USERNAME:-admin}"
export KC_BOOTSTRAP_ADMIN_PASSWORD="${KC_BOOTSTRAP_ADMIN_PASSWORD:-changeme}"

exec "$PWD/keycloak/bin/kc.sh" start-dev \
    --http-host=0.0.0.0 \
    --http-port="${PORT}"
