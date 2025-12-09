#!/bin/sh
set -e

echo "==> Starting Umami Analytics"

# Generate HASH_SALT if not provided
if [ -z "$HASH_SALT" ]; then
    export HASH_SALT=$(cat /dev/urandom | tr -dc 'a-zA-Z0-9' | fold -w 32 | head -n 1)
    echo "Generated HASH_SALT"
fi

# Run database migrations
echo "==> Running database migrations"
yarn prisma migrate deploy

# Start Umami (using standalone server for Next.js 15+)
echo "==> Starting Next.js standalone server"
exec node .next/standalone/server.js
