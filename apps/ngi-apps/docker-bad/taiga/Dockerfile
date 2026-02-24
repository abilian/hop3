# Taiga Dockerfile for Hop3
# Open source agile project management
# NOTE: Taiga has backend (Django) + frontend (Angular) + async (Celery)
# This is a simplified single-container deployment

FROM debian:bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive

# Install dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-venv \
    python3-dev \
    build-essential \
    libpq-dev \
    libxml2-dev \
    libxslt1-dev \
    libffi-dev \
    libjpeg-dev \
    libfreetype6-dev \
    gettext \
    curl \
    ca-certificates \
    git \
    nginx \
    && rm -rf /var/lib/apt/lists/*

# Install Node.js for frontend build
RUN curl -fsSL https://deb.nodesource.com/setup_18.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Create taiga user
RUN useradd -m -d /home/taiga -s /bin/bash taiga

# Create directories
RUN mkdir -p /home/taiga/backend /home/taiga/frontend /home/taiga/media /home/taiga/static \
    && chown -R taiga:taiga /home/taiga

WORKDIR /home/taiga

# Clone Taiga backend
ARG TAIGA_VERSION=6.8.1
RUN git clone --depth 1 --branch ${TAIGA_VERSION} https://github.com/kaleidos-ventures/taiga-back.git /home/taiga/backend \
    && chown -R taiga:taiga /home/taiga/backend

# Clone Taiga frontend
RUN git clone --depth 1 --branch ${TAIGA_VERSION} https://github.com/kaleidos-ventures/taiga-front-dist.git /home/taiga/frontend \
    && chown -R taiga:taiga /home/taiga/frontend

# Install Python dependencies
RUN python3 -m venv /home/taiga/venv \
    && /home/taiga/venv/bin/pip install --no-cache-dir -U pip wheel \
    && /home/taiga/venv/bin/pip install --no-cache-dir -r /home/taiga/backend/requirements.txt \
    && /home/taiga/venv/bin/pip install --no-cache-dir gunicorn psycopg2-binary

# Configure nginx
RUN echo 'server {\n\
    listen 8080;\n\
    server_name _;\n\
    \n\
    large_client_header_buffers 4 32k;\n\
    client_max_body_size 50M;\n\
    charset utf-8;\n\
    \n\
    location / {\n\
        root /home/taiga/frontend/dist;\n\
        try_files $uri $uri/ /index.html;\n\
    }\n\
    \n\
    location /api {\n\
        proxy_pass http://127.0.0.1:8001/api;\n\
        proxy_set_header Host $http_host;\n\
        proxy_set_header X-Real-IP $remote_addr;\n\
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;\n\
        proxy_set_header X-Forwarded-Proto $scheme;\n\
    }\n\
    \n\
    location /admin {\n\
        proxy_pass http://127.0.0.1:8001/admin;\n\
        proxy_set_header Host $http_host;\n\
        proxy_set_header X-Real-IP $remote_addr;\n\
    }\n\
    \n\
    location /static {\n\
        alias /home/taiga/static;\n\
    }\n\
    \n\
    location /media {\n\
        alias /home/taiga/media;\n\
    }\n\
}\n\
' > /etc/nginx/sites-available/taiga \
    && ln -sf /etc/nginx/sites-available/taiga /etc/nginx/sites-enabled/default

# Create backend settings
RUN echo 'from .common import *\n\
import os\n\
\n\
DEBUG = False\n\
DATABASES = {\n\
    "default": {\n\
        "ENGINE": "django.db.backends.postgresql",\n\
        "NAME": os.getenv("PGDATABASE", "taiga"),\n\
        "USER": os.getenv("PGUSER", "taiga"),\n\
        "PASSWORD": os.getenv("PGPASSWORD", ""),\n\
        "HOST": os.getenv("PGHOST", "localhost"),\n\
        "PORT": os.getenv("PGPORT", "5432"),\n\
    }\n\
}\n\
\n\
MEDIA_ROOT = "/home/taiga/media"\n\
STATIC_ROOT = "/home/taiga/static"\n\
\n\
SECRET_KEY = os.getenv("TAIGA_SECRET_KEY", "change-me")\n\
\n\
SITES = {\n\
    "front": {\n\
        "scheme": os.getenv("TAIGA_SCHEME", "http"),\n\
        "domain": os.getenv("TAIGA_DOMAIN", "localhost"),\n\
        "name": "front"\n\
    },\n\
    "api": {\n\
        "scheme": os.getenv("TAIGA_SCHEME", "http"),\n\
        "domain": os.getenv("TAIGA_DOMAIN", "localhost"),\n\
        "name": "api"\n\
    },\n\
}\n\
\n\
ENABLE_TELEMETRY = os.getenv("ENABLE_TELEMETRY", "False").lower() == "true"\n\
\n\
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"\n\
' > /home/taiga/backend/settings/local.py

# Create startup script
RUN echo '#!/bin/bash\n\
set -e\n\
\n\
# Database configuration (Hop3 injects PG* vars)\n\
export PGHOST="${PGHOST:-localhost}"\n\
export PGPORT="${PGPORT:-5432}"\n\
export PGDATABASE="${PGDATABASE:-taiga}"\n\
export PGUSER="${PGUSER:-taiga}"\n\
export PGPASSWORD="${PGPASSWORD:-}"\n\
export TAIGA_SECRET_KEY="${TAIGA_SECRET_KEY:-$(head -c 32 /dev/urandom | base64)}"\n\
export TAIGA_DOMAIN="${TAIGA_DOMAIN:-localhost}"\n\
export TAIGA_SCHEME="${TAIGA_SCHEME:-http}"\n\
\n\
# Configure frontend\n\
cat > /home/taiga/frontend/dist/conf.json << EOF\n\
{\n\
    "api": "${TAIGA_SCHEME}://${TAIGA_DOMAIN}/api/v1/",\n\
    "eventsUrl": null,\n\
    "debug": false,\n\
    "publicRegisterEnabled": true,\n\
    "feedbackEnabled": false,\n\
    "supportUrl": "https://tree.taiga.io/support",\n\
    "privacyPolicyUrl": null,\n\
    "termsOfServiceUrl": null,\n\
    "maxUploadFileSize": 104857600,\n\
    "contribPlugins": []\n\
}\n\
EOF\n\
\n\
cd /home/taiga/backend\n\
\n\
# Run migrations\n\
/home/taiga/venv/bin/python manage.py migrate --noinput || true\n\
\n\
# Collect static files\n\
/home/taiga/venv/bin/python manage.py collectstatic --noinput\n\
\n\
# Load initial data if empty\n\
/home/taiga/venv/bin/python manage.py loaddata initial_user || true\n\
/home/taiga/venv/bin/python manage.py loaddata initial_project_templates || true\n\
\n\
# Ensure proper ownership\n\
chown -R taiga:taiga /home/taiga\n\
\n\
# Start nginx\n\
nginx\n\
\n\
# Start gunicorn as taiga user\n\
exec su taiga -c "cd /home/taiga/backend && /home/taiga/venv/bin/gunicorn taiga.wsgi:application -b 127.0.0.1:8001 --workers 2"\n\
' > /usr/local/bin/start-taiga.sh \
    && chmod +x /usr/local/bin/start-taiga.sh

# Environment
ENV PORT=8080
ENV DJANGO_SETTINGS_MODULE=settings.local

# Data volumes
VOLUME /home/taiga/media

EXPOSE 8080

CMD ["/usr/local/bin/start-taiga.sh"]
