#!/bin/bash
# Easy!Appointments cron script for Hop3
# Syncs calendar appointments

set -eu

CODE_DIR="${HOP3_CODE_DIR:-/app/code}"
HOP3_USER="${HOP3_USER:-www-data}"

cd "${CODE_DIR}"
exec sudo -E -u ${HOP3_USER} php index.php console sync
