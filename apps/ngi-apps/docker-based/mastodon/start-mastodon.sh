#!/bin/bash
set -e
cd /home/mastodon/app

# Required environment variables - fail fast if not set
: "${PORT:?ERROR: PORT is required}"
: "${PGHOST:?ERROR: PGHOST is required}"
: "${PGPORT:?ERROR: PGPORT is required}"
: "${PGDATABASE:?ERROR: PGDATABASE is required}"
: "${PGUSER:?ERROR: PGUSER is required}"
: "${PGPASSWORD:?ERROR: PGPASSWORD is required}"
: "${REDIS_HOST:?ERROR: REDIS_HOST is required}"
: "${REDIS_PORT:?ERROR: REDIS_PORT is required}"

# Set environment variables
export RAILS_ENV=production
export LOCAL_DOMAIN="${LOCAL_DOMAIN:-localhost}"
export DB_HOST="$PGHOST"
export DB_PORT="$PGPORT"
export DB_NAME="$PGDATABASE"
export DB_USER="$PGUSER"
export DB_PASS="$PGPASSWORD"

# Generate secrets if not provided (persist these in production!)
export SECRET_KEY_BASE="${SECRET_KEY_BASE:-$(head -c 64 /dev/urandom | base64)}"
export OTP_SECRET="${OTP_SECRET:-$(head -c 64 /dev/urandom | base64)}"

# Rails 7 encryption keys (required by Mastodon 4.x)
export ACTIVE_RECORD_ENCRYPTION_PRIMARY_KEY="${ACTIVE_RECORD_ENCRYPTION_PRIMARY_KEY:-$(head -c 32 /dev/urandom | base64)}"
export ACTIVE_RECORD_ENCRYPTION_DETERMINISTIC_KEY="${ACTIVE_RECORD_ENCRYPTION_DETERMINISTIC_KEY:-$(head -c 32 /dev/urandom | base64)}"
export ACTIVE_RECORD_ENCRYPTION_KEY_DERIVATION_SALT="${ACTIVE_RECORD_ENCRYPTION_KEY_DERIVATION_SALT:-$(head -c 32 /dev/urandom | base64)}"

# Run migrations (assets precompiled at build time)
bundle exec rails db:migrate

# Start Mastodon web
exec su mastodon -c "cd /home/mastodon/app && bundle exec puma -C config/puma.rb -b tcp://0.0.0.0:$PORT"
