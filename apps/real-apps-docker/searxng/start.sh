#!/bin/bash
set -e

# Required environment variables - fail fast if not set
: "${PORT:?ERROR: PORT is required}"

# Optional with defaults
export SEARXNG_SECRET_KEY="${SEARXNG_SECRET_KEY:-$(head -c 32 /dev/urandom | base64)}"

# Generate settings from template
envsubst < /etc/searxng/settings.yml.template > /etc/searxng/settings.yml
chown searxng:searxng /etc/searxng/settings.yml

# Configuration path
export SEARXNG_SETTINGS_PATH="/etc/searxng/settings.yml"

# Run SearXNG as searxng user
exec su searxng -c "cd /usr/local/searxng/searxng-src && \
    /usr/local/searxng/venv/bin/python -m searx.webapp"
