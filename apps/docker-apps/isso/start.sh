#!/bin/bash
set -e

# Required environment variables - fail fast if not set
: "${PORT:?ERROR: PORT is required}"

# Optional with defaults
export ISSO_HOST="${ISSO_HOST:-http://localhost:${PORT}}"
export ISSO_SALT="${ISSO_SALT:-$(head -c 16 /dev/urandom | base64)}"

# Generate config from template
envsubst < /etc/isso/isso.cfg.template > /etc/isso/isso.cfg
chown isso:isso /etc/isso/isso.cfg

# Ensure proper ownership
chown -R isso:isso /var/lib/isso

# Run Isso as isso user
exec su isso -c "/opt/isso/bin/isso -c /etc/isso/isso.cfg run"
