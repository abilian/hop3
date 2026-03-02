#!/bin/bash
set -e

# Validate required environment variables (injected by Hop3)
: "${PORT:?ERROR: PORT is required}"
: "${PGHOST:?ERROR: PGHOST is required}"
: "${PGPORT:?ERROR: PGPORT is required}"
: "${PGDATABASE:?ERROR: PGDATABASE is required}"
: "${PGUSER:?ERROR: PGUSER is required}"
: "${PGPASSWORD:?ERROR: PGPASSWORD is required}"

# Build DATABASE_URL from components
export DATABASE_URL="postgresql://${PGUSER}:${PGPASSWORD}@${PGHOST}:${PGPORT}/${PGDATABASE}"

# Optional with defaults
export NEXTAUTH_URL="${NEXTAUTH_URL:-http://localhost:${PORT}}"
export NEXTAUTH_SECRET="${NEXTAUTH_SECRET:-$(head -c 32 /dev/urandom | base64)}"
export ENCRYPTION_KEY="${ENCRYPTION_KEY:-$(head -c 48 /dev/urandom | base64 | tr -dc a-zA-Z0-9 | head -c 64)}"
export CRON_SECRET="${CRON_SECRET:-$(head -c 32 /dev/urandom | base64)}"

# Run database migrations
cd /app/packages/database
npx prisma migrate deploy --schema=schema.prisma

# Run Formbricks
exec su formbricks -c "cd /app/apps/web && pnpm start"
