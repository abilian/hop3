#!/bin/bash
# Matomo archiving cron script

set -eu

DATA_DIR="${HOP3_DATA_DIR:-/app/data}"
CODE_DIR="${HOP3_CODE_DIR:-/app/code}"

cd "${CODE_DIR}"

echo "==> Running Matomo archive"
php "${CODE_DIR}/console" core:archive --url="${HOP3_APP_ORIGIN:-http://localhost}" || true

echo "==> Archive complete"
