---
tutorial:
  name: drf-hop3-tutorial
  env:
    PYTHONDONTWRITEBYTECODE: "1"
    SECRET_KEY: "dev-only-secret-key-not-for-production"
    DEBUG: "true"
  teardown:
    - rm -rf hop3-tuto-drf venv 2>/dev/null || true
    - hop3 app destroy --app hop3-tuto-drf -y 2>/dev/null || true
---

# Deploying Django REST Framework on Hop3

This guide walks you through deploying a Django REST Framework (DRF) API on Hop3. DRF is the most popular toolkit for building Web APIs with Django.

## Prerequisites

Before you begin, ensure you have:

1. **A Hop3 server** - Follow the [Installation Guide](../../get-started/server-setup.md)
2. **The Hop3 CLI** - Installed on your local machine
3. **Python 3.10+** - Install from [python.org](https://www.python.org/)
4. **Git** - For version control and deployment

Verify your local setup:

```bash exec id=check-python
python3 --version
```

```output regex
Python 3\.[0-9]+\.
```

## Step 1: Create a New DRF Application

```bash exec id=create-project
mkdir hop3-tuto-drf && cd hop3-tuto-drf && python3 -m venv venv
```

```assert file-exists path=hop3-tuto-drf/venv/bin/activate
```

Install Django and DRF:

```bash exec id=install-drf dir=hop3-tuto-drf timeout=60
. venv/bin/activate && pip install django djangorestframework gunicorn
```

```output contains
Successfully installed
```

Create Django project:

```bash exec id=create-django dir=hop3-tuto-drf
. venv/bin/activate && django-admin startproject config . && python manage.py startapp api
```

```assert file-exists path=hop3-tuto-drf/manage.py
```

## Step 2: Configure the Application

Update settings:

```file path=hop3-tuto-drf/config/settings.py
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# SECRET_KEY: a dev-insecure fallback keeps `migrate` and the very first deploy
# working before any secrets are set. Override it in production with
# `hop3 config set --app <app> SECRET_KEY=...` (see the deploy step below).
SECRET_KEY = os.environ.get('SECRET_KEY', 'django-insecure-dev-only-change-me')
DEBUG = os.environ.get('DEBUG', 'False').lower() == 'true'

ALLOWED_HOSTS = os.environ.get('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')

INSTALLED_APPS = [
    'django.contrib.contenttypes',
    'django.contrib.auth',
    'rest_framework',
    'api',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.middleware.common.CommonMiddleware',
]

ROOT_URLCONF = 'config.urls'
WSGI_APPLICATION = 'config.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

REST_FRAMEWORK = {
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
    ],
    'DEFAULT_PARSER_CLASSES': [
        'rest_framework.parsers.JSONParser',
    ],
}

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_TZ = True
```

Create models:

```file path=hop3-tuto-drf/api/models.py
from django.db import models


class Item(models.Model):
    name = models.CharField(max_length=255)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name
```

Create serializers:

```file path=hop3-tuto-drf/api/serializers.py
from rest_framework import serializers
from .models import Item


class ItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = Item
        fields = ['id', 'name', 'price', 'created_at']
```

Create views:

```file path=hop3-tuto-drf/api/views.py
from datetime import datetime
from django.http import HttpResponse
from rest_framework import viewsets, status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from .models import Item
from .serializers import ItemSerializer


def home(request):
    return HttpResponse(f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Welcome to Hop3</title>
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                display: flex;
                justify-content: center;
                align-items: center;
                min-height: 100vh;
                margin: 0;
                background: linear-gradient(135deg, #092e20 0%, #44b78b 100%);
                color: white;
            }}
            .container {{ text-align: center; padding: 2rem; }}
            h1 {{ font-size: 3rem; margin-bottom: 1rem; }}
            p {{ font-size: 1.25rem; opacity: 0.9; }}
            a {{ color: white; margin-top: 1rem; display: inline-block; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Hello from Hop3!</h1>
            <p>Your Django REST Framework API is running.</p>
            <p>Current time: {datetime.now().isoformat()}</p>
            <a href="/api/">API Root</a>
        </div>
    </body>
    </html>
    """)


def up(request):
    return HttpResponse("OK")


@api_view(['GET'])
def health(request):
    return Response({
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "version": "1.0.0"
    })


@api_view(['GET'])
def info(request):
    import django
    return Response({
        "name": "hop3-tuto-drf",
        "version": "1.0.0",
        "django_version": django.get_version(),
        "framework": "Django REST Framework"
    })


class ItemViewSet(viewsets.ModelViewSet):
    queryset = Item.objects.all()
    serializer_class = ItemSerializer
```

Configure URLs:

```file path=hop3-tuto-drf/config/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from api import views

router = DefaultRouter()
router.register(r'items', views.ItemViewSet)

urlpatterns = [
    path('', views.home),
    path('up', views.up),
    path('health', views.health),
    path('api/info', views.info),
    path('api/', include(router.urls)),
]
```

## Step 3: Initialize Database

```bash exec id=migrate dir=hop3-tuto-drf
. venv/bin/activate && python manage.py migrate
```

```output contains
Applying
```

## Step 4: Create Requirements

```bash exec id=freeze-requirements dir=hop3-tuto-drf
. venv/bin/activate && pip freeze > requirements.txt
```

```bash exec id=check-requirements dir=hop3-tuto-drf
cat requirements.txt | grep -i djangorestframework
```

```output contains
djangorestframework
```

## Step 5: Test the Application

Test that the application starts correctly (skipped in automated tests - local server tests are flaky):

```bash skip
. venv/bin/activate && python manage.py runserver 0.0.0.0:8000 &
sleep 2
curl -s http://localhost:8000/health
```

Verify the project structure:

```bash exec id=verify-structure dir=hop3-tuto-drf
ls -la manage.py requirements.txt config/
```

```output contains
manage.py
```

## Step 6: Create Deployment Configuration

```file path=hop3-tuto-drf/.gitignore
venv/
__pycache__/
*.pyc
.env
db.sqlite3
```

```file path=hop3-tuto-drf/Procfile
prerun: python manage.py migrate --noinput
web: gunicorn config.wsgi --bind 0.0.0.0:$PORT
```

```file path=hop3-tuto-drf/hop3.toml
[metadata]
id = "hop3-tuto-drf"
version = "1.0.0"
title = "My DRF API"

[build]
packages = ["python3", "python3-pip"]

[run]
start = "gunicorn config.wsgi --bind 0.0.0.0:$PORT"
before-run = "python manage.py migrate --noinput"

[env]
PYTHONUNBUFFERED = "1"
DJANGO_SETTINGS_MODULE = "config.settings"

[port]
web = 8000

[healthcheck]
path = "/up"
timeout = 30
interval = 60
```

## Deploy to Hop3

The following steps require a Hop3 server.

### Initialize (First Time Only)

```bash skip
hop3 init --ssh root@your-server.example.com
```

### Deploy

Deploy the application (first deployment creates the app):

```bash exec id=deploy dir=hop3-tuto-drf timeout=120
hop3 deploy hop3-tuto-drf
```

### Set Environment Variables

Harden the deployment: replace the dev-insecure fallback `SECRET_KEY` with a
real one, and set `ALLOWED_HOSTS` and the hostname for the application:

```bash exec id=set-secret-key timeout=30
hop3 config set --app hop3-tuto-drf SECRET_KEY=drf-insecure-changeme-for-production
```

```bash exec id=set-allowed-hosts timeout=30
hop3 config set --app hop3-tuto-drf ALLOWED_HOSTS=hop3-tuto-drf.$HOP3_TEST_DOMAIN,localhost,127.0.0.1
```

```bash exec id=set-hostname timeout=30
hop3 config set --app hop3-tuto-drf HOST_NAME=hop3-tuto-drf.$HOP3_TEST_DOMAIN
```

### Apply Configuration

Redeploy to apply the configuration:

```bash exec id=redeploy dir=hop3-tuto-drf timeout=120
hop3 deploy hop3-tuto-drf
```

```output contains
deployed successfully
```

### Verify Deployment

```bash exec id=check-status timeout=30
hop3 app status --app hop3-tuto-drf
```

```output contains
hop3-tuto-drf
```

```bash exec id=check-health timeout=30
curl -s http://hop3-tuto-drf.$HOP3_TEST_DOMAIN/up
```

```output contains
OK
```

View logs:

```bash skip
hop3 app logs --app hop3-tuto-drf

# Your app will be available at:
# http://hop3-tuto-drf.your-hop3-server.example.com
```

### Managing Your Application

```bash skip
# Restart the application
hop3 app restart --app hop3-tuto-drf

# View/set environment variables
hop3 config show --app hop3-tuto-drf
hop3 config set --app hop3-tuto-drf NEW_VAR=value

# Scale workers
hop3 ps scale --app hop3-tuto-drf web=2
```

## Advanced Configuration

### Authentication

```python
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.TokenAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
}
```

### Pagination

```python
REST_FRAMEWORK = {
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 10,
}
```

### Filtering

```python
# pip install django-filter
REST_FRAMEWORK = {
    'DEFAULT_FILTER_BACKENDS': ['django_filters.rest_framework.DjangoFilterBackend']
}
```

### PostgreSQL

```python
DATABASES = {
    'default': dj_database_url.config(default=os.environ.get('DATABASE_URL'))
}
```

## Example hop3.toml

```toml
[metadata]
id = "hop3-tuto-drf"
version = "1.0.0"

[build]
before-build = ["python manage.py collectstatic --noinput"]

[run]
start = "gunicorn config.wsgi --bind 0.0.0.0:$PORT --workers 2"
before-run = "python manage.py migrate --noinput"

[port]
web = 8000

[healthcheck]
path = "/up"

[[provider]]
name = "postgres"
plan = "standard"
```
