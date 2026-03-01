#!/bin/bash
set -e

# Required environment variables - fail fast if not set
: "${PORT:?ERROR: PORT is required}"

# Optional with defaults (non-critical)
export ISSO_HOST="${ISSO_HOST:-http://localhost:${PORT}}"
export ISSO_SALT="${ISSO_SALT:-$(head -c 16 /dev/urandom | base64)}"

# Update config
sed -i "s|host = .*|host = ${ISSO_HOST}|" /etc/isso/isso.cfg
sed -i "s|listen = .*|listen = http://0.0.0.0:${PORT}|" /etc/isso/isso.cfg
sed -i "s|salt = .*|salt = ${ISSO_SALT}|" /etc/isso/isso.cfg

# Ensure proper ownership
chown -R isso:isso /var/lib/isso

# Run Isso as isso user
exec su isso -c "/opt/isso/bin/isso -c /etc/isso/isso.cfg run"
