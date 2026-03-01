#!/bin/bash
set -e

# Validate required environment variables (injected by Hop3)
: "${MYSQL_HOST:?ERROR: MYSQL_HOST is required}"
: "${MYSQL_PORT:?ERROR: MYSQL_PORT is required}"
: "${MYSQL_DATABASE:?ERROR: MYSQL_DATABASE is required}"
: "${MYSQL_USER:?ERROR: MYSQL_USER is required}"
: "${MYSQL_PASSWORD:?ERROR: MYSQL_PASSWORD is required}"

# Start Apache
exec apache2ctl -D FOREGROUND
