#!/bin/bash
# Nextcloud preview cleanup script

set -eu

CODE_DIR="${HOP3_CODE_DIR:-/app/code}"

echo "==> Running Nextcloud preview cleanup"
php "${CODE_DIR}/occ" preview:cleanup || true
