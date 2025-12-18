#!/bin/bash
# Startup script for Linkding with PostgreSQL configuration

set -e

echo "==> Starting Linkding"

cd /app

# Configure PostgreSQL from PG* environment variables
if [ -n "$PGHOST" ]; then
    export LD_DB_ENGINE=postgres
    export LD_DB_HOST="$PGHOST"
    export LD_DB_PORT="${PGPORT:-5432}"
    export LD_DB_DATABASE="${PGDATABASE:-linkding}"
    export LD_DB_USER="${PGUSER:-linkding}"
    export LD_DB_PASSWORD="$PGPASSWORD"

    echo "==> Database config:"
    echo "    Engine: PostgreSQL"
    echo "    Host: $LD_DB_HOST"
    echo "    Port: $LD_DB_PORT"
    echo "    Database: $LD_DB_DATABASE"
    echo "    User: $LD_DB_USER"
else
    echo "==> Using SQLite database"
fi

# Create superuser if credentials provided
if [ -n "$LD_SUPERUSER_NAME" ] && [ -n "$LD_SUPERUSER_PASSWORD" ]; then
    echo "==> Superuser will be created: $LD_SUPERUSER_NAME"
fi

# Run migrations
echo "==> Running database migrations..."
python manage.py migrate --skip-checks

# Create superuser if needed
if [ -n "$LD_SUPERUSER_NAME" ] && [ -n "$LD_SUPERUSER_PASSWORD" ]; then
    echo "==> Creating superuser..."
    python manage.py createsuperuser --username "$LD_SUPERUSER_NAME" --email "${LD_SUPERUSER_EMAIL:-admin@localhost}" --noinput 2>/dev/null || true
    # Set password (createsuperuser doesn't set it with noinput)
    python manage.py shell -c "
from django.contrib.auth import get_user_model
User = get_user_model()
try:
    user = User.objects.get(username='$LD_SUPERUSER_NAME')
    user.set_password('$LD_SUPERUSER_PASSWORD')
    user.save()
except User.DoesNotExist:
    pass
" 2>/dev/null || true
fi

# Collect static files
echo "==> Collecting static files..."
python manage.py collectstatic --noinput --clear

echo "==> Starting Gunicorn server..."
exec gunicorn siteroot.wsgi:application \
    --bind "0.0.0.0:${LD_SERVER_PORT:-9090}" \
    --workers 2 \
    --threads 4 \
    --access-logfile -
