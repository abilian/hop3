---
tutorial:
  name: pyramid-hop3-tutorial
  env:
    PYTHONDONTWRITEBYTECODE: "1"
  teardown:
    - rm -rf hop3-tuto-pyramid venv 2>/dev/null || true
    - hop3 app destroy --app hop3-tuto-pyramid -y 2>/dev/null || true
---

# Deploying Pyramid on Hop3

This guide walks you through deploying a Pyramid application on Hop3. Pyramid is a flexible, enterprise-grade Python web framework.

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

## Step 1: Create a New Pyramid Application

```bash exec id=create-project
mkdir hop3-tuto-pyramid && cd hop3-tuto-pyramid && python3 -m venv venv
```

```assert file-exists path=hop3-tuto-pyramid/venv/bin/activate
```

Install Pyramid:

```bash exec id=install-pyramid dir=hop3-tuto-pyramid timeout=60
. venv/bin/activate && pip install pyramid pyramid_jinja2 waitress
```

```output contains
Successfully installed
```

## Step 2: Create the Application

```file path=hop3-tuto-pyramid/app.py
import os
import json
from datetime import datetime

from pyramid.config import Configurator
from pyramid.response import Response
from pyramid.view import view_config


# In-memory storage
items = {
    1: {"id": 1, "name": "Item 1", "price": 9.99},
    2: {"id": 2, "name": "Item 2", "price": 19.99},
}
next_id = 3


@view_config(route_name='home')
def home(request):
    html = f"""
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
                background: linear-gradient(135deg, #bf0f0f 0%, #8b0000 100%);
                color: white;
            }}
            .container {{ text-align: center; padding: 2rem; }}
            h1 {{ font-size: 3rem; margin-bottom: 1rem; }}
            p {{ font-size: 1.25rem; opacity: 0.9; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Hello from Hop3!</h1>
            <p>Your Pyramid application is running.</p>
            <p>Current time: {datetime.now().isoformat()}</p>
        </div>
    </body>
    </html>
    """
    return Response(html, content_type='text/html')


@view_config(route_name='up')
def up(request):
    return Response('OK')


@view_config(route_name='health', renderer='json')
def health(request):
    return {
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "version": "1.0.0"
    }


@view_config(route_name='info', renderer='json')
def info(request):
    import sys
    return {
        "name": "hop3-tuto-pyramid",
        "version": "1.0.0",
        "python_version": sys.version,
        "framework": "Pyramid"
    }


@view_config(route_name='list_items', renderer='json')
def list_items(request):
    return list(items.values())


@view_config(route_name='get_item', renderer='json')
def get_item(request):
    item_id = int(request.matchdict['id'])
    if item_id not in items:
        request.response.status = 404
        return {"error": "Not found"}
    return items[item_id]


@view_config(route_name='create_item', renderer='json', request_method='POST')
def create_item(request):
    global next_id
    data = request.json_body
    item = {"id": next_id, "name": data["name"], "price": data["price"]}
    items[next_id] = item
    next_id += 1
    request.response.status = 201
    return item


@view_config(route_name='delete_item', request_method='DELETE')
def delete_item(request):
    item_id = int(request.matchdict['id'])
    if item_id not in items:
        request.response.status = 404
        return Response(json.dumps({"error": "Not found"}), content_type='application/json')
    del items[item_id]
    return Response(status=204)


def main(global_config=None, **settings):
    config = Configurator(settings=settings)
    config.include('pyramid_jinja2')

    # Routes
    config.add_route('home', '/')
    config.add_route('up', '/up')
    config.add_route('health', '/health')
    config.add_route('info', '/api/info')
    config.add_route('list_items', '/api/items')
    config.add_route('create_item', '/api/items')
    config.add_route('get_item', '/api/items/{id}')
    config.add_route('delete_item', '/api/items/{id}')

    config.scan()
    return config.make_wsgi_app()


app = main()


if __name__ == '__main__':
    from waitress import serve
    port = int(os.environ.get('PORT', 6543))
    print(f"Starting server on port {port}")
    serve(app, host='0.0.0.0', port=port)
```

```assert file-exists path=hop3-tuto-pyramid/app.py
```

## Step 3: Create Requirements

```bash exec id=freeze-requirements dir=hop3-tuto-pyramid
. venv/bin/activate && pip freeze > requirements.txt
```

```bash exec id=check-requirements dir=hop3-tuto-pyramid
cat requirements.txt | grep -i pyramid | head -1
```

```output contains
pyramid
```

## Step 4: Test the Application

Test locally (skipped in automated tests - local server tests are flaky):

```bash skip
. venv/bin/activate && python app.py &
sleep 2
curl -s http://localhost:6543/health
```

## Step 5: Create Deployment Configuration

```file path=hop3-tuto-pyramid/.gitignore
venv/
__pycache__/
*.pyc
.env
```

```file path=hop3-tuto-pyramid/Procfile
web: python app.py
```

```file path=hop3-tuto-pyramid/hop3.toml
[metadata]
id = "hop3-tuto-pyramid"
version = "1.0.0"
title = "My Pyramid Application"

[build]
packages = ["python3", "python3-pip"]

[run]
start = "python app.py"

[env]
PYTHONUNBUFFERED = "1"

[port]
web = 6543

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

### Set Environment Variables

```bash skip
hop3 config set --app hop3-tuto-pyramid SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
```

### Deploy

Deploy the application (first deployment creates the app):

```bash exec id=deploy dir=hop3-tuto-pyramid timeout=120
hop3 deploy hop3-tuto-pyramid
```

```output contains
deployed successfully
```

### Set Hostname

Configure the hostname for nginx proxy:

```bash exec id=set-hostname timeout=30
hop3 config set --app hop3-tuto-pyramid HOST_NAME=hop3-tuto-pyramid.$HOP3_TEST_DOMAIN
```

### Apply Configuration

Redeploy to apply the hostname configuration:

```bash exec id=redeploy dir=hop3-tuto-pyramid timeout=120
hop3 deploy hop3-tuto-pyramid
```

```output contains
deployed successfully
```

### Verify Deployment

```bash exec id=check-status timeout=30
hop3 app status --app hop3-tuto-pyramid
```

```output contains
hop3-tuto-pyramid
```

```bash exec id=check-health timeout=30
curl -s http://hop3-tuto-pyramid.$HOP3_TEST_DOMAIN/up
```

```output contains
OK
```

View logs:

```bash skip
hop3 app logs --app hop3-tuto-pyramid

# Your app will be available at:
# http://hop3-tuto-pyramid.your-hop3-server.example.com
```

### Managing Your Application

```bash skip
# Restart the application
hop3 app restart --app hop3-tuto-pyramid

# View/set environment variables
hop3 config show --app hop3-tuto-pyramid
hop3 config set --app hop3-tuto-pyramid NEW_VAR=value

# Scale workers
hop3 ps scale --app hop3-tuto-pyramid web=2
```

## Advanced Configuration

### SQLAlchemy Integration

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

def main(global_config, **settings):
    engine = create_engine(settings.get('sqlalchemy.url'))
    config.registry['dbsession_factory'] = sessionmaker(bind=engine)
```

### Authentication with pyramid_authsanity

```python
config.include('pyramid_authsanity')
```

### Gunicorn for Production

```procfile
web: gunicorn --paste production.ini --bind 0.0.0.0:$PORT
```

## Example hop3.toml

```toml
[metadata]
id = "hop3-tuto-pyramid"
version = "1.0.0"

[build]
[run]
start = "python app.py"

[port]
web = 6543

[healthcheck]
path = "/up"

[[provider]]
name = "postgres"
plan = "standard"
```
