#!/bin/bash
# Umami start script for Hop3

set -eu

DATA_DIR="${HOP3_DATA_DIR:-/app/data}"
CODE_DIR="${HOP3_CODE_DIR:-/app/code}"
PKG_DIR="${HOP3_PKG_DIR:-/app/pkg}"
HOP3_USER="${HOP3_USER:-www-data}"

[[ ! -f "${DATA_DIR}/env.sh" ]] && sed -e "s,HASH_SALT=.*,HASH_SALT=$(pwgen -1s 32)," "${PKG_DIR}/env.sh.template" > "${DATA_DIR}/env.sh"

echo "==> Changing ownership"
chown -R ${HOP3_USER}:${HOP3_USER} "${DATA_DIR}"

# standard env vars
export NODE_ENV=production
export DATABASE_URL="postgresql://${POSTGRES_USERNAME:-umami}:${POSTGRES_PASSWORD:-}@${POSTGRES_HOST:-localhost}:${POSTGRES_PORT:-5432}/${POSTGRES_DATABASE:-umami}"
export FORCE_SSL=1
export PORT=3000
export DISABLE_UPDATES=1
export DATABASE_TYPE=postgresql

# source it before the build, lets one set COLLECT_API_ENDPOINT
source "${DATA_DIR}/env.sh"

# Create pgcrypto extension if needed
PGPASSWORD=${POSTGRES_PASSWORD:-} psql -h ${POSTGRES_HOST:-localhost} -p ${POSTGRES_PORT:-5432} -U ${POSTGRES_USERNAME:-umami} -d ${POSTGRES_DATABASE:-umami} -c "CREATE EXTENSION IF NOT EXISTS pgcrypto;"

# this tramples a whole lot of code directories listed in the manifest. setting VERCEL=1 skips build-geo
echo "=> Running build script that generates the migrations"
cd "${CODE_DIR}" && VERCEL=1 yarn run build

echo "=> Running migrations"
cd "${CODE_DIR}" && su -s /bin/bash ${HOP3_USER} -c "yarn run update-db"

echo "==> Starting Umami"
cd "${CODE_DIR}" && exec su -s /bin/bash ${HOP3_USER} -c "yarn next start"
