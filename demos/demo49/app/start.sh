#!/bin/bash
# Startup script for Taiga with PostgreSQL configuration

set -e

# Set Taiga URL from HOST_NAME or default
TAIGA_URL="${TAIGA_URL:-https://${HOST_NAME:-localhost}}"
export TAIGA_URL

# Configure Taiga backend settings
export DJANGO_SETTINGS_MODULE="settings.local"
export TAIGA_SECRET_KEY="${TAIGA_SECRET_KEY:-$(head -c 32 /dev/urandom | base64)}"
export TAIGA_SITES_DOMAIN="${HOST_NAME:-localhost}"

# Generate frontend config
envsubst < /var/www/taiga/conf.json.template > /var/www/taiga/conf.json
echo "Generated frontend conf.json with TAIGA_URL=${TAIGA_URL}"

# Run database migrations
cd /taiga-back
echo "Running database migrations..."
python manage.py migrate --noinput || true

# Collect static files
echo "Collecting static files..."
python manage.py collectstatic --noinput || true

# Create admin user if not exists
echo "Ensuring admin user exists..."
python manage.py shell -c "
from django.contrib.auth import get_user_model
User = get_user_model()
if not User.objects.filter(username='admin').exists():
    User.objects.create_superuser('admin', 'admin@example.com', 'admin123')
    print('Created admin user')
else:
    print('Admin user already exists')
" || true

# Start supervisor
echo "Starting Taiga services..."
exec /usr/bin/supervisord -c /etc/supervisor/conf.d/supervisord.conf
