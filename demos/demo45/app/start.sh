#!/bin/sh
# Startup script for Ruby/Sinatra with PostgreSQL

set -e

echo "Starting Ruby/Sinatra app..."
echo "PGHOST: ${PGHOST:-not set}"
echo "PGDATABASE: ${PGDATABASE:-not set}"
echo "PGUSER: ${PGUSER:-not set}"
echo "PGPORT: ${PGPORT:-not set}"

exec ruby app.rb
