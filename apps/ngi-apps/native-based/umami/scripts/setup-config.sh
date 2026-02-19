#!/bin/bash
set -e
export DATABASE_URL="postgresql://${PGUSER:-umami}:${PGPASSWORD:-}@${PGHOST:-localhost}:${PGPORT:-5432}/${PGDATABASE:-umami}"
export PORT="${PORT:-8080}"
export APP_SECRET="${APP_SECRET:-$(head -c 32 /dev/urandom | base64)}"

# Write to .env for the app to read
cat > .env << EOF
DATABASE_URL=${DATABASE_URL}
PORT=${PORT}
APP_SECRET=${APP_SECRET}
EOF

# Run migrations
npx prisma migrate deploy
echo "Umami configuration created"
