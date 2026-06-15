# Deploying Django REST Framework on Hop3

This guide walks you through deploying a Django REST Framework (DRF) API on Hop3. DRF is the most popular toolkit for building Web APIs with Django.

## Prerequisites

Before you begin, ensure you have:

1. **A Hop3 server** - Follow the [Installation Guide](../../get-started/server-setup.md)
2. **The Hop3 CLI** - Installed on your local machine
3. **Python 3.10+** - Install from [python.org](https://www.python.org/)
4. **Git** - For version control and deployment

Verify your local setup:

```bash
python3 --version
```

## Step 1: Create a New DRF Application

```bash
mkdir hop3-tuto-drf && cd hop3-tuto-drf && python3 -m venv venv
```

Install Django and DRF:

```bash
. venv/bin/activate && pip install django djangorestframework gunicorn
```

```console
Successfully installed
```

Create Django project:

```bash
. venv/bin/activate && django-admin startproject config . && python manage.py startapp api
```

## Step 2: Configure the Application

Update settings:

```python
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

```python
from django.db import models

class Item(models.Model):
    name = models.CharField(max_length=255)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name
```

Create serializers:

```python
from rest_framework import serializers
from .models import Item

class ItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = Item
        fields = ['id', 'name', 'price', 'created_at']
```

Create views:

```python
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

```python
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

```bash
. venv/bin/activate && python manage.py migrate
```

```console
Applying
```

## Step 4: Create Requirements

```bash
. venv/bin/activate && pip freeze > requirements.txt
```

```bash
cat requirements.txt | grep -i djangorestframework
```

```console
djangorestframework
```

## Step 5: Test the Application

Test that the application starts correctly (skipped in automated tests - local server tests are flaky):

```bash
. venv/bin/activate && python manage.py runserver 0.0.0.0:8000 &
sleep 2
curl -s http://localhost:8000/health
```

Verify the project structure:

```bash
ls -la manage.py requirements.txt config/
```

```console
manage.py
```

## Step 6: Create Deployment Configuration

```text
venv/
__pycache__/
*.pyc
.env
db.sqlite3
```

```procfile
prerun: python manage.py migrate --noinput
web: gunicorn config.wsgi --bind 0.0.0.0:$PORT
```

```toml
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
# DRF/Django needs SECRET_KEY in production. Generated once on the first deploy,
# persisted, and reused — never committed or rotated (ADR 046).
SECRET_KEY = { generate = "hex", length = 50 }
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

```bash
hop3 init --ssh root@your-server.example.com
```

### Deploy

Deploy the application (first deployment creates the app):

```bash
hop3 deploy hop3-tuto-drf
```

### Set Environment Variables

`SECRET_KEY` is generated automatically on the first deploy (see `hop3.toml`
`[env]`). Set `ALLOWED_HOSTS` and the hostname for the application:

```bash
hop3 config set --app hop3-tuto-drf ALLOWED_HOSTS=hop3-tuto-drf.$HOP3_TEST_DOMAIN,localhost,127.0.0.1
```

```bash
hop3 config set --app hop3-tuto-drf HOST_NAME=hop3-tuto-drf.$HOP3_TEST_DOMAIN
```

### Apply Configuration

Redeploy to apply the configuration:

```bash
hop3 deploy hop3-tuto-drf
```

```console
deployed successfully
```

### Verify Deployment

```bash
hop3 app status --app hop3-tuto-drf
```

```console
hop3-tuto-drf
```

```bash
curl -s http://hop3-tuto-drf.$HOP3_TEST_DOMAIN/up
```

```console
OK
```

View logs:

```bash
hop3 app logs --app hop3-tuto-drf

# Your app will be available at:
# http://hop3-tuto-drf.your-hop3-server.example.com
```

### Managing Your Application

```bash
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

[env]
SECRET_KEY = { generate = "hex", length = 50 }

[port]
web = 8000

[healthcheck]
path = "/up"

[[provider]]
name = "postgres"
plan = "standard"
```
