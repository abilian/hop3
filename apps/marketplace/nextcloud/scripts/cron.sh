#!/bin/bash
# Nextcloud cron script

set -eu

CODE_DIR="${HOP3_CODE_DIR:-/app/code}"

echo "==> Running Nextcloud cron"
php -f "${CODE_DIR}/cron.php"
