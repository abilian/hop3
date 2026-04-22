#!/bin/bash
set -e

: "${PORT:?ERROR: PORT is required}"

mkdir -p data

export ROCKET_ADDRESS="0.0.0.0"
export ROCKET_PORT="${PORT}"
export DATA_FOLDER="${DATA_FOLDER:-$PWD/data}"
export WEB_VAULT_FOLDER="${WEB_VAULT_FOLDER:-$PWD/web-vault}"

if [ -z "$DATABASE_URL" ]; then
    export DATABASE_URL="$DATA_FOLDER/db.sqlite3"
fi

# Cargo should have produced target/release/vaultwarden via the Rust
# toolchain auto-detected from Cargo.toml.
exec ./target/release/vaultwarden
