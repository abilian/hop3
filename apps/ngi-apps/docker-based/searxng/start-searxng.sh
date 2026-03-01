#!/bin/bash
set -e

# Required environment variables - fail fast if not set
: "${PORT:?ERROR: PORT is required}"

# Optional with defaults (non-critical)
export SEARXNG_SECRET="${SEARXNG_SECRET:-$(head -c 32 /dev/urandom | base64)}"

# Configuration
export SEARXNG_SETTINGS_PATH="/etc/searxng/settings.yml"

# Update settings with port and secret
sed -i "s/port: 8080/port: ${PORT}/" /etc/searxng/settings.yml
sed -i "s/secret_key: .*/secret_key: \"${SEARXNG_SECRET}\"/" /etc/searxng/settings.yml

# Run SearXNG as searxng user
exec su searxng -c "cd /usr/local/searxng/searxng-src && \
    /usr/local/searxng/venv/bin/python -m searx.webapp"
