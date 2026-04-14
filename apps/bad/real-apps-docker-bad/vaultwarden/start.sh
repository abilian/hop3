#!/bin/bash
set -e

: "${PORT:?ERROR: PORT is required}"

mkdir -p /data

export ROCKET_ADDRESS="0.0.0.0"
export ROCKET_PORT="${PORT}"
export DATA_FOLDER="/data"
export WEB_VAULT_FOLDER="/opt/web-vault"

if [ -z "$DATABASE_URL" ]; then
    export DATABASE_URL="/data/db.sqlite3"
fi

exec /usr/local/bin/vaultwarden
