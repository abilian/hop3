#!/bin/bash
set -e

# Validate required environment variables (injected by Hop3)
: "${PORT:?ERROR: PORT is required}"
: "${DATABASE_URL:?ERROR: DATABASE_URL is required}"

cd /home/umami/app

# Umami uses DATABASE_URL directly
exec su umami -c "cd /home/umami/app && npm start"
