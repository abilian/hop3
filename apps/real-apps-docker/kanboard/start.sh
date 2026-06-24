#!/bin/bash
set -e

# Validate required environment variables (injected by Hop3)
: "${MYSQL_HOST:?ERROR: MYSQL_HOST is required}"
: "${MYSQL_PORT:?ERROR: MYSQL_PORT is required}"
: "${MYSQL_DATABASE:?ERROR: MYSQL_DATABASE is required}"
: "${MYSQL_USER:?ERROR: MYSQL_USER is required}"
: "${MYSQL_PASSWORD:?ERROR: MYSQL_PASSWORD is required}"

# Migrate the schema to completion BEFORE serving. Kanboard otherwise migrates
# lazily on the first web request; Hop3's readiness probe (a real GET on a 0.5s
# poll loop with a 3s timeout) interrupts that mid-DDL — picodb takes no lock —
# and the retry re-runs the half-applied version, failing with "Table ...
# already exists". `cli db:migrate` runs once, serialized, before any request
# arrives. Run as www-data so any files Kanboard writes stay Apache-owned.
su -s /bin/bash www-data -c "cd /var/www/html && php cli db:migrate"

# Start Apache
exec apache2ctl -D FOREGROUND
