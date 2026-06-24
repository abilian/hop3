# Deploying Flask on Hop3

This guide walks you through deploying a Flask application on Hop3. By the end, you'll have a production-ready Python web application running on your own infrastructure.

## Prerequisites

Before you begin, ensure you have:

1. **A Hop3 server** - Follow the [Installation Guide](../../get-started/server-setup.md) if you haven't set one up yet
2. **The Hop3 CLI** - Installed on your local machine
3. **Python 3.10+** - Install from [python.org](https://www.python.org/) or via your package manager
4. **pip** - Python package manager (comes with Python)
5. **Git** - For version control and deployment

Verify your local setup:

```bash
python3 --version
```

```bash
pip3 --version
```

## Step 1: Create a New Flask Application

Create the project directory and virtual environment:

```bash
mkdir hop3-tuto-flask && cd hop3-tuto-flask && python3 -m venv venv
```

Activate the virtual environment and install Flask:

```bash
. venv/bin/activate && pip install flask gunicorn python-dotenv
```

```console
Successfully installed
```

## Step 2: Create the Application

Create the main application file:

```python
import os
from datetime import datetime
from flask import Flask, jsonify

app = Flask(__name__)

# Configuration
app.config['DEBUG'] = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
# SECRET_KEY is required in production - no insecure default
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY')
if not app.config['SECRET_KEY'] and not app.config['DEBUG']:
    raise ValueError("SECRET_KEY environment variable is required in production")

@app.route('/')
def index():
    """Welcome page."""
    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Welcome to Hop3</title>
        <style>
            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                display: flex;
                justify-content: center;
                align-items: center;
                min-height: 100vh;
                margin: 0;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
            }
            .container {
                text-align: center;
                padding: 2rem;
            }
            h1 { font-size: 3rem; margin-bottom: 1rem; }
            p { font-size: 1.25rem; opacity: 0.9; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Hello from Hop3!</h1>
            <p>Your Flask application is running.</p>
            <p>Current time: ''' + datetime.now().isoformat() + '''</p>
        </div>
    </body>
    </html>
    '''

@app.route('/up')
def up():
    """Health check endpoint for Hop3."""
    return 'OK', 200

@app.route('/health')
def health():
    """Detailed health check."""
    return jsonify({
        'status': 'ok',
        'timestamp': datetime.now().isoformat(),
        'version': '1.0.0'
    })

@app.route('/api/info')
def info():
    """API information endpoint."""
    return jsonify({
        'name': 'hop3-tuto-flask',
        'version': '1.0.0',
        'python_version': os.sys.version,
        'environment': os.environ.get('FLASK_ENV', 'production')
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
```

## Step 3: Create Requirements File

Generate the requirements file:

```bash
. venv/bin/activate && pip freeze > requirements.txt
```

Verify the requirements:

```bash
cat requirements.txt | grep -E "^(Flask|gunicorn)" | head -2
```

```console
Flask
```

```console
gunicorn
```

## Step 4: Add Configuration Files

Create a configuration module for different environments:

```python
import os

class Config:
    """Base configuration."""
    SECRET_KEY = os.environ.get('SECRET_KEY')  # Required - no default
    DEBUG = False
    TESTING = False

    # Database
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', 'sqlite:///app.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False

class DevelopmentConfig(Config):
    """Development configuration."""
    DEBUG = True

class ProductionConfig(Config):
    """Production configuration."""
    DEBUG = False

    # Ensure we have a proper secret key in production
    @property
    def SECRET_KEY(self):
        key = os.environ.get('SECRET_KEY')
        if not key:
            raise ValueError('SECRET_KEY must be set in production')
        return key

class TestingConfig(Config):
    """Testing configuration."""
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'

config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}
```

Create a WSGI entry point for Gunicorn:

```python
import os
from app import app

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
```

## Step 5: Verify the Application Works

Test that the application starts correctly (skipped in automated tests - local server tests are flaky):

```bash
. venv/bin/activate && timeout 3 python app.py &
sleep 2
curl -s http://localhost:5000/health
```

Verify the project structure:

```bash
ls -la *.py requirements.txt
```

```console
app.py
```

```console
requirements.txt
```

## Step 6: Create Deployment Configuration

### Create a Procfile

Create a `Procfile` in your project root:

```procfile
# Main web process (using Gunicorn)
web: gunicorn wsgi:app --bind 0.0.0.0:$PORT --workers 2 --threads 4 --worker-class gthread
```

### Create hop3.toml

Create a `hop3.toml` for advanced configuration:

```toml
[metadata]
id = "hop3-tuto-flask"
version = "1.0.0"
title = "My Flask Application"

[build]
packages = ["python3", "python3-pip", "python3-venv"]

[run]
start = "gunicorn wsgi:app --bind 0.0.0.0:$PORT --workers 2 --threads 4"

[env]
# Flask requires SECRET_KEY in production (see the app config) or it refuses to
# start. Generated once on the first deploy, persisted, and reused — never
# committed or rotated (ADR 046).
SECRET_KEY = { generate = "hex", length = 32 }
FLASK_ENV = "production"
PYTHONUNBUFFERED = "1"

[port]
web = 5000

[healthcheck]
path = "/up"
timeout = 30
interval = 60
```

Verify the deployment files exist:

```bash
ls -la Procfile hop3.toml
```

```console
Procfile
```

```console
hop3.toml
```

## Step 7: Initialize Git Repository

Create a `.gitignore` file:

```text
# Virtual environment
venv/
.venv/
ENV/

# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
*.egg-info/
dist/
build/

# Environment
.env
.env.local
.env.*.local

# IDE
.idea/
.vscode/
*.swp
*.swo

# OS files
.DS_Store
Thumbs.db

# Database
*.db
*.sqlite3

# Logs
*.log

# Testing
.pytest_cache/
.coverage
htmlcov/
```

Initialize the repository:

```bash
git init
```

```console
Initialized empty Git repository
```

```bash
git add .
```

```bash
git commit -m "Initial Flask application"
```

```console
Initial Flask application
```

## Step 8: Deploy to Hop3

The following steps require a Hop3 server. Log into yours first — for example, `hop3 login --ssh root@your-server.com` — so the CLI knows where to deploy.

### Configure the CLI

If this is your first deployment, initialize Hop3:

```bash
hop3 init --ssh root@your-server.example.com
```

### Deploy

Deploy the application (first deployment creates the app). `SECRET_KEY` is generated automatically from the `hop3.toml` `[env]` declaration before the app boots, so the first deploy comes up cleanly — no placeholder, no crash:

```bash
hop3 deploy --app hop3-tuto-flask
```

### Set Hostname

Point nginx at the app:

```bash
hop3 config set --app hop3-tuto-flask HOST_NAME=hop3-tuto-flask.$HOP3_TEST_DOMAIN
```

### Apply Configuration

Redeploy to apply the configuration:

```bash
hop3 deploy --app hop3-tuto-flask
```

Wait for the application to start:

```bash
sleep 5
```

## Step 9: Verify Deployment

Check your application status:

```bash
hop3 app status --app hop3-tuto-flask
```

```console
hop3-tuto-flask
```

```bash
curl -s http://hop3-tuto-flask.$HOP3_TEST_DOMAIN/up
```

```console
OK
```

View logs:

```bash
hop3 app logs --app hop3-tuto-flask
```

Open your application:

```bash
# Your app will be available at:
# http://hop3-tuto-flask.your-hop3-server.example.com
```

## Managing Your Application

### Restart the Application

```bash
hop3 app restart --app hop3-tuto-flask
```

### Run Commands in the Application Context

```bash
hop3 run --app hop3-tuto-flask python -c "from app import app; print(app.config)"
```

### View and Manage Environment Variables

```bash
# List all variables
hop3 config show --app hop3-tuto-flask

# Set a variable
hop3 config set --app hop3-tuto-flask NEW_VARIABLE=value

# Remove a variable
hop3 config unset --app hop3-tuto-flask OLD_VARIABLE
```

### Scaling

```bash
# Check current processes
hop3 ps --app hop3-tuto-flask

# Scale web workers
hop3 ps scale --app hop3-tuto-flask web=2
```

## Advanced Configuration

### Adding a Database (PostgreSQL with SQLAlchemy)

Install SQLAlchemy and PostgreSQL driver:

```bash
pip install flask-sqlalchemy psycopg2-binary
pip freeze > requirements.txt
```

Update `app.py`:

```python
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///app.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)

    def __repr__(self):
        return f'<User {self.username}>'

@app.route('/health')
def health():
    try:
        db.session.execute(db.text('SELECT 1'))
        db_status = 'connected'
    except Exception as e:
        db_status = f'error: {str(e)}'

    return jsonify({
        'status': 'ok',
        'database': db_status
    })
```

Create and attach database:

```bash
hop3 addons create postgres hop3-tuto-flask-db
hop3 addons attach hop3-tuto-flask hop3-tuto-flask-db
```

Run migrations:

```bash
hop3 run --app hop3-tuto-flask flask db upgrade
```

### Adding Flask-Migrate for Database Migrations

```bash
pip install flask-migrate
```

Initialize migrations:

```python
from flask_migrate import Migrate

migrate = Migrate(app, db)
```

Update `Procfile`:

```procfile
prerun: flask db upgrade
web: gunicorn wsgi:app --bind 0.0.0.0:$PORT
```

### Adding Redis for Caching

Install Flask-Caching with Redis:

```bash
pip install flask-caching redis
```

Configure caching:

```python
from flask_caching import Cache

app.config['CACHE_TYPE'] = 'redis'
app.config['CACHE_REDIS_URL'] = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')

cache = Cache(app)

@app.route('/cached')
@cache.cached(timeout=60)
def cached_view():
    return jsonify({'cached': True, 'time': datetime.now().isoformat()})
```

Attach Redis:

```bash
hop3 addons create redis hop3-tuto-flask-redis
hop3 addons attach hop3-tuto-flask hop3-tuto-flask-redis
```

### Background Tasks with Celery

Install Celery:

```bash
pip install celery[redis]
```

Create `tasks.py`:

```python
from celery import Celery

def make_celery(app):
    celery = Celery(
        app.import_name,
        backend=app.config.get('CELERY_RESULT_BACKEND'),
        broker=app.config.get('CELERY_BROKER_URL')
    )
    celery.conf.update(app.config)
    return celery

# In app.py
app.config['CELERY_BROKER_URL'] = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
app.config['CELERY_RESULT_BACKEND'] = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')

celery = make_celery(app)

@celery.task
def send_async_email(email_data):
    # Send email
    pass
```

Add worker to `Procfile`:

```procfile
web: gunicorn wsgi:app --bind 0.0.0.0:$PORT
worker: celery -A app.celery worker --loglevel=info
```

### Flask Blueprints for Larger Applications

For larger applications, organize with blueprints:

```python
# api/routes.py
from flask import Blueprint, jsonify

api_bp = Blueprint('api', __name__, url_prefix='/api')

@api_bp.route('/users')
def get_users():
    return jsonify([])

# app.py
from api.routes import api_bp
app.register_blueprint(api_bp)
```

### Request Logging

Add request logging middleware:

```python
import logging
from flask import request

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s: %(message)s'
)
logger = logging.getLogger(__name__)

@app.before_request
def log_request():
    logger.info(f'{request.method} {request.path}')

@app.after_request
def log_response(response):
    logger.info(f'{request.method} {request.path} - {response.status_code}')
    return response
```

### CORS Configuration

Install Flask-CORS:

```bash
pip install flask-cors
```

Configure CORS:

```python
from flask_cors import CORS

# SECURITY: Always specify allowed origins explicitly - never use '*' in production
allowed_origins = os.environ.get('ALLOWED_ORIGINS')
if not allowed_origins:
    raise ValueError("ALLOWED_ORIGINS must be set (e.g., 'https://example.com,https://app.example.com')")
CORS(app, origins=allowed_origins.split(','))
```

## Troubleshooting

### Application Won't Start

Check the logs for errors:

```bash
hop3 app logs --app hop3-tuto-flask --tail
```

Common issues:
- **Missing SECRET_KEY**: Set it with `hop3 config set`
- **Module not found**: Ensure all dependencies are in `requirements.txt`
- **Port binding**: Ensure Gunicorn binds to `0.0.0.0:$PORT`

### Database Connection Issues

Verify the database is attached:

```bash
hop3 config show --app hop3-tuto-flask | grep DATABASE
```

Test the connection:

```bash
hop3 run --app hop3-tuto-flask python -c "from app import db; db.session.execute(db.text('SELECT 1'))"
```

### Import Errors

Ensure your application structure is correct:

```
hop3-tuto-flask/
├── app.py
├── wsgi.py
├── config.py
├── requirements.txt
├── Procfile
└── hop3.toml
```

### Gunicorn Workers

For CPU-bound applications, increase workers:

```procfile
web: gunicorn wsgi:app --bind 0.0.0.0:$PORT --workers 4
```

For I/O-bound applications, use async workers:

```bash
pip install gevent
```

```procfile
web: gunicorn wsgi:app --bind 0.0.0.0:$PORT --workers 2 --worker-class gevent
```

## Next Steps

- **[CLI Reference](../../reference/cli.md)** - Complete command reference
- **[hop3.toml Reference](../../reference/config.md)** - Full configuration options
- **[Backup and Restore Guide](../../guides/backup-restore.md)** - Protect your data

## Example Files

### Complete hop3.toml for Flask

```toml
# hop3.toml - Flask Application

[metadata]
id = "hop3-tuto-flask"
version = "1.0.0"
title = "My Flask Application"
author = "Your Name <you@example.com>"

[build]
packages = ["python3", "python3-pip", "libpq-dev"]

[run]
start = "gunicorn wsgi:app --bind 0.0.0.0:$PORT --workers 2 --threads 4"
before-run = "flask db upgrade"

[env]
SECRET_KEY = { generate = "hex", length = 32 }
FLASK_ENV = "production"
PYTHONUNBUFFERED = "1"

[port]
web = 5000

[healthcheck]
path = "/up"
timeout = 30
interval = 60

[[provider]]
name = "postgres"
plan = "standard"

[[provider]]
name = "redis"
plan = "basic"
```

### Complete Procfile for Flask

```procfile
# Procfile - Flask Application

# Build phase
# Pre-run hooks (database migrations)
prerun: flask db upgrade

# Web server
web: gunicorn wsgi:app --bind 0.0.0.0:$PORT --workers 2 --threads 4 --worker-class gthread

# Background worker (optional)
worker: celery -A app.celery worker --loglevel=info

# Beat scheduler (optional)
beat: celery -A app.celery beat --loglevel=info
```
