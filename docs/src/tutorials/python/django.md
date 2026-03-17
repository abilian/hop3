
# Deploying Django on Hop3

This guide walks you through deploying a Django application on Hop3. By the end, you'll have a production-ready Django application running on your own infrastructure.

## Prerequisites

Before you begin, ensure you have:

1. **A Hop3 server** - Follow the [Installation Guide](../../get-started/installation.md) if you haven't set one up yet
2. **The Hop3 CLI** - Installed on your local machine
3. **Python 3.10+** - With pip and venv
4. **PostgreSQL** - Installed locally for development
5. **Git** - For version control and deployment

Verify your local setup:

```bash
python3 --version
```

```text
Python 3.
```

```bash
pip3 --version
```

```text
pip
```

## Step 1: Create a New Django Project

Create a project directory and virtual environment:

```bash
mkdir -p hop3-tuto-django
```

```bash
python3 -m venv venv
```

Install Django and create the project:

```bash
source venv/bin/activate && pip install django gunicorn psycopg2-binary whitenoise dj-database-url python-decouple
```

```text
Successfully installed
```

```bash
source venv/bin/activate && django-admin startproject myproject .
```

Your project structure should look like:

```
hop3-tuto-django/
├── manage.py
├── myproject/
│   ├── __init__.py
│   ├── asgi.py
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
└── venv/
```

## Step 2: Create a Welcome Page

Create a simple app for the homepage:

```bash
source venv/bin/activate && python manage.py startapp pages
```

Create the view in `pages/views.py`:

```python
from django.http import HttpResponse, JsonResponse
from django.db import connection
import datetime

def home(request):
    return HttpResponse(f"""
        <h1>Hello from Hop3!</h1>
        <p>Your Django application is running.</p>
        <p>Current time: {datetime.datetime.now()}</p>
    """)

def up(request):
    return HttpResponse("OK")

def health(request):
    """Health check endpoint for Hop3."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        return JsonResponse({
            'status': 'ok',
            'database': 'connected'
        })
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=503)
```

Update `myproject/urls.py`:

```python
from django.contrib import admin
from django.urls import path
from pages.views import home, up, health

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', home, name='home'),
    path('up', up, name='up'),
    path('health/', health, name='health'),
]
```

## Step 3: Configure for Production

### Create a Requirements File

Create a minimal `requirements.txt`:

```text
Django>=5.0,<6.0
gunicorn>=21.0
psycopg2-binary>=2.9
whitenoise>=6.6
dj-database-url>=2.1
python-decouple>=3.8
```

### Configure Settings for Production

Create a production-ready settings file. Update `myproject/settings.py`:

```python
import os
from pathlib import Path

# Try to import decouple, fall back to os.environ
try:
    from decouple import config
except ImportError:
    config = lambda key, default=None, cast=str: cast(os.environ.get(key, default)) if os.environ.get(key, default) else default

try:
    import dj_database_url
    HAS_DJ_DATABASE_URL = True
except ImportError:
    HAS_DJ_DATABASE_URL = False

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
# In production, SECRET_KEY must be set - no default provided for security
SECRET_KEY = config('SECRET_KEY', default='django-insecure-dev-only' if os.environ.get('DJANGO_DEVELOPMENT') else None)
if not SECRET_KEY:
    raise ValueError("SECRET_KEY environment variable is required in production")

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = config('DEBUG', default='False', cast=lambda v: v.lower() == 'true')

ALLOWED_HOSTS = config(
    'ALLOWED_HOSTS',
    default='localhost,127.0.0.1',
    cast=lambda v: [h.strip() for h in v.split(',')]
)

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'pages',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'myproject.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'myproject.wsgi.application'

# Database
DATABASE_URL = config('DATABASE_URL', default=None)

if DATABASE_URL and HAS_DJ_DATABASE_URL:
    DATABASES = {
        'default': dj_database_url.parse(DATABASE_URL, conn_max_age=600)
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

# WhiteNoise configuration
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# Media files
MEDIA_URL = '/media/'
MEDIA_ROOT = config('MEDIA_ROOT', default=str(BASE_DIR / 'media'))

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Security settings for production
if not DEBUG:
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = 'DENY'
    CSRF_COOKIE_SECURE = True
    SESSION_COOKIE_SECURE = True

# Logging configuration
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': config('LOG_LEVEL', default='INFO'),
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': config('DJANGO_LOG_LEVEL', default='INFO'),
            'propagate': False,
        },
    },
}
```

### Create Static Directory

```bash
mkdir -p static staticfiles templates
```

## Step 4: Create Deployment Configuration

You can deploy Django apps to Hop3 using either a `Procfile` (simple, Heroku-compatible) or `hop3.toml` (advanced features). You can also use both together.

### Option A: Using a Procfile

Create a `Procfile` in your project root:

```procfile
# Pre-run: Migrations and static files
prerun: python manage.py migrate --noinput && python manage.py collectstatic --noinput

# Main web process
web: gunicorn myproject.wsgi:application --bind 0.0.0.0:$PORT --workers 4
```

### Option B: Using hop3.toml

Create a `hop3.toml` in your project root:

<!-- FIXME: SECRET_KEY should use random generation: SECRET_KEY = { random='true', length=50 }
     This is supported per ADR 002 but needs testing. For now, hardcoded value is used. -->

```toml
[metadata]
id = "hop3-tuto-django"
version = "1.0.0"
title = "My Django Application"

[build]
# Use the local builder - Python toolchain is auto-detected
builder = "local"
packages = ["postgresql-dev", "gcc", "python3-dev"]

[run]
start = "gunicorn myproject.wsgi:application --bind 0.0.0.0:$PORT --workers 4"
before-run = [
    "python manage.py migrate --noinput",
    "python manage.py collectstatic --noinput"
]

[env]
DJANGO_SETTINGS_MODULE = "myproject.settings"
SECRET_KEY = "CHANGEME-generate-a-secure-random-key-for-production"

[port]
web = 8000

[healthcheck]
path = "/health/"
timeout = 30
interval = 60

[[provider]]
name = "postgres"
plan = "standard"
```

## Step 5: Configure Gunicorn

Create `gunicorn.conf.py` for more control:

```python
import os
import multiprocessing

# Bind to the PORT environment variable (Hop3 sets this)
bind = f"0.0.0.0:{os.environ.get('PORT', '8000')}"

# Worker configuration
workers = int(os.environ.get('WEB_CONCURRENCY', multiprocessing.cpu_count() * 2 + 1))
worker_class = 'sync'
worker_connections = 1000
timeout = 30
keepalive = 2

# Logging
accesslog = '-'  # stdout
errorlog = '-'   # stderr
loglevel = os.environ.get('LOG_LEVEL', 'info').lower()

# Process naming
proc_name = 'hop3-tuto-django'

# Server mechanics
preload_app = True
daemon = False
```

## Step 6: Verify the Application Works

Run migrations and verify the setup:

```bash
source venv/bin/activate && python manage.py migrate --noinput
```

```text
Operations to perform
```

Collect static files:

```bash
source venv/bin/activate && python manage.py collectstatic --noinput
```

```text
static files
```

Run Django's system checks:

```bash
source venv/bin/activate && python manage.py check
```

```text
System check identified no issues
```

Verify the project structure is complete:

```bash
ls -la
```

```text
manage.py
```

```text
Procfile
```

```text
hop3.toml
```

```text
requirements.txt
```

## Step 7: Initialize Git Repository

Create a `.gitignore` file:

```text
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
venv/
ENV/
.venv/

# Django
*.log
local_settings.py
db.sqlite3
media/

# Static files (collected)
staticfiles/

# Environment
.env
.envrc

# IDE
.idea/
.vscode/
*.swp
*.swo

# OS
.DS_Store
Thumbs.db
```

Initialize the repository:

```bash
git init
```

```text
Initialized empty Git repository
```

```bash
git add .
```

```bash
git commit -m "Initial Django application"
```

```text
Initial Django application
```

## Step 8: Deploy to Hop3

The following steps require a Hop3 server. Set the `HOP3_SERVER` environment variable to your server address before running these commands.

### Configure the CLI

If this is your first deployment, initialize Hop3:

```bash
hop3 init --ssh root@your-server.example.com
```

### Create and Attach a Database

```bash
hop3 addons:create postgres hop3-tuto-django-db
hop3 addons:attach hop3-tuto-django hop3-tuto-django-db
```

### Set Environment Variables

```bash
# Generate and set the secret key
hop3 config:set hop3-tuto-django SECRET_KEY=$(python -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())')

# Set Django configuration
hop3 config:set hop3-tuto-django DEBUG=false
hop3 config:set hop3-tuto-django ALLOWED_HOSTS=hop3-tuto-django.your-hop3-server.example.com
hop3 config:set hop3-tuto-django DJANGO_SETTINGS_MODULE=myproject.settings
```

### Deploy

Deploy the application (first deployment creates the app):

```bash
hop3 deploy hop3-tuto-django
```

```text
deployed successfully
```

### Set Environment Variables

Set the SECRET_KEY, ALLOWED_HOSTS, and hostname for the application:

```bash
hop3 config:set hop3-tuto-django SECRET_KEY=django-insecure-changeme-for-production
```

```bash
hop3 config:set hop3-tuto-django ALLOWED_HOSTS=hop3-tuto-django.$HOP3_TEST_DOMAIN,localhost,127.0.0.1
```

```bash
hop3 config:set hop3-tuto-django HOST_NAME=hop3-tuto-django.$HOP3_TEST_DOMAIN
```

### Apply Configuration

Redeploy to apply the configuration:

```bash
hop3 deploy hop3-tuto-django
```

Wait for the application to start:

```bash
sleep 5
```

## Step 9: Verify Deployment

Check your application status:

```bash
hop3 app:status hop3-tuto-django
```

```text
hop3-tuto-django
```

```bash
curl -s http://hop3-tuto-django.$HOP3_TEST_DOMAIN/up
```

```text
OK
```

View logs:

```bash
hop3 app:logs hop3-tuto-django
```

Open your application:

```bash
# Your app will be available at:
# http://hop3-tuto-django.your-hop3-server.example.com
```

### Create a Superuser

```bash
hop3 run hop3-tuto-django python manage.py createsuperuser
```

## Managing Your Application

### Run Database Migrations

Migrations run automatically during deployment via `prerun`. To run manually:

```bash
hop3 run hop3-tuto-django python manage.py migrate
```

### Run Django Shell

```bash
hop3 run hop3-tuto-django python manage.py shell
```

### Run Management Commands

```bash
hop3 run hop3-tuto-django python manage.py loaddata fixtures.json
hop3 run hop3-tuto-django python manage.py custom_command
```

### View and Manage Environment Variables

```bash
# List all variables
hop3 config:show hop3-tuto-django

# Set a variable
hop3 config:set hop3-tuto-django NEW_VARIABLE=value

# Remove a variable
hop3 config:unset hop3-tuto-django OLD_VARIABLE

# Restart to apply changes
hop3 app:restart hop3-tuto-django
```

### Scaling

```bash
# Check current processes
hop3 ps hop3-tuto-django

# Scale web workers
hop3 ps:scale hop3-tuto-django web=2
```

## Advanced Configuration

### Background Tasks with Celery

Install Celery:

```bash
pip install celery redis
pip freeze > requirements.txt
```

Create `myproject/celery.py`:

```python
import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myproject.settings')

app = Celery('myproject')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()
```

Update `myproject/__init__.py`:

```python
from .celery import app as celery_app

__all__ = ('celery_app',)
```

Add Celery settings to `myproject/settings.py`:

```python
# Celery Configuration
CELERY_BROKER_URL = config('REDIS_URL', default='redis://localhost:6379/0')
CELERY_RESULT_BACKEND = config('REDIS_URL', default='redis://localhost:6379/0')
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE
```

Add worker processes to `Procfile`:

```procfile
web: gunicorn myproject.wsgi:application -c gunicorn.conf.py
worker: celery -A myproject worker --loglevel=info
beat: celery -A myproject beat --loglevel=info
```

Attach a Redis addon:

```bash
hop3 addons:create redis hop3-tuto-django-redis
hop3 addons:attach hop3-tuto-django hop3-tuto-django-redis
```

### Django Q (Database-backed Task Queue)

If you prefer not to use Redis, Django Q can use your existing database:

```bash
pip install django-q2
```

Add to `INSTALLED_APPS`:

```python
INSTALLED_APPS = [
    # ...
    'django_q',
]
```

Configure in settings:

```python
Q_CLUSTER = {
    'name': 'myproject',
    'workers': 4,
    'timeout': 90,
    'django_redis': 'default',
    'orm': 'default',  # Use database as broker
}
```

Add to `Procfile`:

```procfile
worker: python manage.py qcluster
```

### Media Files (User Uploads)

For file uploads, configure the media storage path:

```python
# settings.py
MEDIA_URL = '/media/'
MEDIA_ROOT = config('MEDIA_ROOT', default=str(BASE_DIR / 'media'))
```

Set the storage path on Hop3:

```bash
hop3 config:set hop3-tuto-django MEDIA_ROOT=/var/hop3/apps/hop3-tuto-django/data/media
```

For serving media files in production, add to `myproject/urls.py`:

```python
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    # ... your urls ...
]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
```

For production, configure your reverse proxy (nginx) to serve media files, or use WhiteNoise with a custom storage backend.

### Django REST Framework

Add DRF to your project:

```bash
pip install djangorestframework
pip freeze > requirements.txt
```

Add to `INSTALLED_APPS`:

```python
INSTALLED_APPS = [
    # ...
    'rest_framework',
]
```

Configure in settings:

```python
REST_FRAMEWORK = {
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',
        'rest_framework.authentication.TokenAuthentication',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
}
```

### Django Channels (WebSockets)

For real-time features:

```bash
pip install channels channels-redis
```

Update `INSTALLED_APPS` and add channel layers:

```python
INSTALLED_APPS = [
    'daphne',  # Add before django apps
    # ...
    'channels',
]

ASGI_APPLICATION = 'myproject.asgi.application'

CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels_redis.core.RedisChannelLayer',
        'CONFIG': {
            'hosts': [config('REDIS_URL', default='redis://localhost:6379/0')],
        },
    },
}
```

Create `myproject/asgi.py`:

```python
import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myproject.settings')

application = ProtocolTypeRouter({
    'http': get_asgi_application(),
    # Add websocket routing here
})
```

Update `Procfile` for ASGI:

```procfile
web: daphne -b 0.0.0.0 -p $PORT myproject.asgi:application
```

### Caching with Redis

```python
# settings.py
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': config('REDIS_URL', default='redis://localhost:6379/1'),
    }
}

# Session backend (optional - use cache for sessions)
SESSION_ENGINE = 'django.contrib.sessions.backends.cache'
SESSION_CACHE_ALIAS = 'default'
```

## Backup and Restore

### Create a Backup

Before major changes, always backup:

```bash
hop3 backup:create hop3-tuto-django
```

This backs up:
- Application source code
- Database (PostgreSQL dump)
- Environment variables
- Media files (uploads)

### Restore from Backup

```bash
hop3 backup:list hop3-tuto-django
hop3 backup:restore <backup-id>
hop3 app:restart hop3-tuto-django
```

## Troubleshooting

### Application Won't Start

Check the logs for errors:

```bash
hop3 app:logs hop3-tuto-django --tail
```

Common issues:

- **Missing SECRET_KEY**: Set it with `hop3 config:set`
- **Database not connected**: Ensure the addon is attached and `DATABASE_URL` is set
- **Static files not found**: Ensure `collectstatic` runs in `prerun`
- **Module not found**: Check `requirements.txt` includes all dependencies

### Database Connection Issues

Verify the database is attached:

```bash
hop3 config:show hop3-tuto-django | grep DATABASE
```

Test the connection:

```bash
hop3 run hop3-tuto-django python manage.py dbshell
```

### Static Files Not Loading

1. Ensure WhiteNoise is in `MIDDLEWARE` (after `SecurityMiddleware`)
2. Check that `collectstatic` runs during deployment
3. Verify `STATIC_ROOT` is set correctly
4. Ensure `STATICFILES_STORAGE` uses WhiteNoise

Run manually to debug:

```bash
hop3 run hop3-tuto-django python manage.py collectstatic --noinput
```

### Migration Errors

If migrations fail during deployment:

```bash
# Check migration status
hop3 run hop3-tuto-django python manage.py showmigrations

# Run migrations manually with verbose output
hop3 run hop3-tuto-django python manage.py migrate --verbosity=2
```

### Import Errors

Ensure all packages are in `requirements.txt`:

```bash
# Regenerate requirements
pip freeze > requirements.txt

# Or check what's installed
hop3 run hop3-tuto-django pip list
```

### Gunicorn Workers Timing Out

Increase timeout in `gunicorn.conf.py`:

```python
timeout = 120  # Increase from default 30
```

Or for specific slow requests, consider using async workers:

```python
worker_class = 'gevent'
```

And add `gevent` to `requirements.txt`.

## Performance Optimization

### Database Connection Pooling

Use `dj-database-url` with connection pooling:

```python
DATABASES = {
    'default': dj_database_url.parse(
        DATABASE_URL,
        conn_max_age=600,  # Keep connections open for 10 minutes
        conn_health_checks=True,
    )
}
```

### Caching

Add caching middleware for anonymous users:

```python
MIDDLEWARE = [
    'django.middleware.cache.UpdateCacheMiddleware',
    # ... other middleware ...
    'django.middleware.cache.FetchFromCacheMiddleware',
]

CACHE_MIDDLEWARE_SECONDS = 300
CACHE_MIDDLEWARE_KEY_PREFIX = 'hop3-tuto-django'
```

### Query Optimization

Use Django Debug Toolbar in development to identify slow queries:

```bash
pip install django-debug-toolbar
```

## Next Steps

- **[CLI Reference](../../reference/cli.md)** - Complete command reference
- **[hop3.toml Reference](../../reference/config.md)** - Full configuration options
- **[Backup and Restore Guide](../../guides/backup-restore.md)** - Protect your data
- **[Migration Guide](../migration-guide.md)** - Migrate from Heroku or other platforms

## Example Files

### Complete hop3.toml for Django

```toml
# hop3.toml - Django Application

[metadata]
id = "hop3-tuto-django"
version = "1.0.0"
title = "My Django Application"
author = "Your Name <you@example.com>"

[build]
# Use the local builder - Python toolchain is auto-detected
builder = "local"
packages = ["postgresql-dev", "gcc", "python3-dev", "libffi-dev"]

[run]
start = "gunicorn myproject.wsgi:application -c gunicorn.conf.py"
before-run = [
    "python manage.py migrate --noinput",
    "python manage.py collectstatic --noinput"
]
packages = ["postgresql"]

[env]
DJANGO_SETTINGS_MODULE = "myproject.settings"
PYTHONUNBUFFERED = "1"

[port]
web = 8000

[healthcheck]
path = "/health/"
timeout = 30
interval = 60

[backup]
enabled = true
schedule = "0 3 * * *"
retention = 14

[[provider]]
name = "postgres"
plan = "standard"
version = "15"

[[provider]]
name = "redis"
plan = "basic"
```

### Complete Procfile for Django

```procfile
# Procfile - Django Application

# Build phase
# Pre-run hooks (migrations and static files)
prerun: python manage.py migrate --noinput && python manage.py collectstatic --noinput

# Web server
web: gunicorn myproject.wsgi:application -c gunicorn.conf.py

# Background worker (Celery)
worker: celery -A myproject worker --loglevel=info

# Scheduled tasks (Celery Beat)
beat: celery -A myproject beat --loglevel=info
```

### Complete requirements.txt

```
Django>=5.0,<6.0
gunicorn>=21.0
psycopg2-binary>=2.9
whitenoise>=6.6
dj-database-url>=2.1
python-decouple>=3.8
celery>=5.3
redis>=5.0
```
