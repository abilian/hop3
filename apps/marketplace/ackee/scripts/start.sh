#!/bin/bash
# Ackee start script for Hop3

set -eu

DATA_DIR="${HOP3_DATA_DIR:-/app/data}"
PKG_DIR="${HOP3_PKG_DIR:-/app/pkg}"
HOP3_USER="${HOP3_USER:-www-data}"

if [[ ! -f "${DATA_DIR}/env" ]]; then
    cp "${PKG_DIR}/templates/env.template" "${DATA_DIR}/env"
fi

sed -e "s,ACKEE_MONGODB=.*,ACKEE_MONGODB=${MONGODB_URL:-mongodb://${MONGODB_USERNAME:-ackee}:${MONGODB_PASSWORD:-}@${MONGODB_HOST:-localhost}:${MONGODB_PORT:-27017}/${MONGODB_DATABASE:-ackee}}," -i "${DATA_DIR}/env"

# Link env file
ln -sf "${DATA_DIR}/env" /app/code/.env

echo "==> Changing ownership"
chown -R ${HOP3_USER}:${HOP3_USER} "${DATA_DIR}"

export NODE_ENV=production

echo "==> Starting Ackee"
exec su -s /bin/bash ${HOP3_USER} -c "cd /app/code && npm run server"
