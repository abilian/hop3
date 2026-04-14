#!/bin/bash
set -e

: "${PORT:?ERROR: PORT is required}"

cd /opt/gotosocial

export GTS_HOST="${GTS_HOST:-localhost}"
export GTS_BIND_ADDRESS="0.0.0.0"
export GTS_PORT="${PORT}"
export GTS_DB_TYPE="${GTS_DB_TYPE:-sqlite}"
export GTS_DB_ADDRESS="${GTS_DB_ADDRESS:-/data/gotosocial.sqlite}"
export GTS_STORAGE_LOCAL_BASE_PATH="${GTS_STORAGE_LOCAL_BASE_PATH:-/data/storage}"
export GTS_LETSENCRYPT_ENABLED="false"
export GTS_WEB_ASSET_BASE_DIR="/opt/gotosocial/web/assets"
export GTS_WEB_TEMPLATE_BASE_DIR="/opt/gotosocial/web/template"

mkdir -p "$GTS_STORAGE_LOCAL_BASE_PATH"

exec ./gotosocial --config-path "" server start
