#!/bin/sh
set -e

echo "==> Starting Filebrowser"

# Create database directory if needed
mkdir -p /app/database

# Initialize database if it doesn't exist
if [ ! -f /app/database/filebrowser.db ]; then
    echo "==> Initializing Filebrowser database..."
    /app/filebrowser config init --database /app/database/filebrowser.db
    /app/filebrowser users add admin admin --database /app/database/filebrowser.db --perm.admin
fi

echo "==> Starting Filebrowser server..."
exec /app/filebrowser \
    --database /app/database/filebrowser.db \
    --root /srv \
    --address 0.0.0.0 \
    --port 8080
