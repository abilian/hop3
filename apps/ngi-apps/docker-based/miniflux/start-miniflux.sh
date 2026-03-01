#!/bin/bash
set -e

# Required environment variables - fail fast if not set
: "${PORT:?ERROR: PORT is required}"
: "${DATABASE_URL:?ERROR: DATABASE_URL is required}"

# Configure Miniflux
export LISTEN_ADDR="0.0.0.0:${PORT}"

exec /usr/local/bin/miniflux
