# Deploying Falcon on Hop3

This guide walks you through deploying a Falcon application on Hop3. Falcon is a minimalist, high-performance framework for building REST APIs.

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

## Step 1: Create a New Falcon Application

```bash
mkdir hop3-tuto-falcon && cd hop3-tuto-falcon && python3 -m venv venv
```

Install Falcon:

```bash
. venv/bin/activate && pip install falcon uvicorn
```

```console
Successfully installed
```

## Step 2: Create the Application

```python
import os
import json
from datetime import datetime

import falcon
import falcon.asgi

# In-memory storage
items = {
    1: {"id": 1, "name": "Item 1", "price": 9.99},
    2: {"id": 2, "name": "Item 2", "price": 19.99},
}
next_id = 3

class HomeResource:
    async def on_get(self, req, resp):
        resp.content_type = 'text/html'
        resp.text = f"""
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
                    background: linear-gradient(135deg, #1e3a5f 0%, #2c5282 100%);
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
                <p>Your Falcon application is running.</p>
                <p>Current time: {datetime.now().isoformat()}</p>
            </div>
        </body>
        </html>
        """

class UpResource:
    async def on_get(self, req, resp):
        resp.content_type = 'text/plain'
        resp.text = 'OK'

class HealthResource:
    async def on_get(self, req, resp):
        resp.media = {
            "status": "ok",
            "timestamp": datetime.now().isoformat(),
            "version": "1.0.0"
        }

class InfoResource:
    async def on_get(self, req, resp):
        import sys
        resp.media = {
            "name": "hop3-tuto-falcon",
            "version": "1.0.0",
            "python_version": sys.version,
            "framework": "Falcon"
        }

class ItemsResource:
    async def on_get(self, req, resp):
        resp.media = list(items.values())

    async def on_post(self, req, resp):
        global next_id
        data = await req.get_media()
        item = {"id": next_id, "name": data["name"], "price": data["price"]}
        items[next_id] = item
        next_id += 1
        resp.status = falcon.HTTP_201
        resp.media = item

class ItemResource:
    async def on_get(self, req, resp, item_id):
        item_id = int(item_id)
        if item_id not in items:
            resp.status = falcon.HTTP_404
            resp.media = {"error": "Not found"}
            return
        resp.media = items[item_id]

    async def on_delete(self, req, resp, item_id):
        item_id = int(item_id)
        if item_id not in items:
            resp.status = falcon.HTTP_404
            resp.media = {"error": "Not found"}
            return
        del items[item_id]
        resp.status = falcon.HTTP_204

app = falcon.asgi.App()

app.add_route('/', HomeResource())
app.add_route('/up', UpResource())
app.add_route('/health', HealthResource())
app.add_route('/api/info', InfoResource())
app.add_route('/api/items', ItemsResource())
app.add_route('/api/items/{item_id}', ItemResource())

if __name__ == '__main__':
    import uvicorn
    port = int(os.environ.get('PORT', 8000))
    uvicorn.run(app, host='0.0.0.0', port=port)
```

## Step 3: Create Requirements

```bash
. venv/bin/activate && pip freeze > requirements.txt
```

```bash
cat requirements.txt | grep -i falcon
```

```console
falcon
```

## Step 4: Test the Application

Test that the application starts correctly (skipped in automated tests - local server tests are flaky):

```bash
. venv/bin/activate && python app.py &
sleep 2
curl -s http://localhost:8000/health
```

Verify the project structure:

```bash
ls -la app.py requirements.txt
```

```console
app.py
```

## Step 5: Create Deployment Configuration

```text
venv/
__pycache__/
*.pyc
.env
```

```procfile
web: uvicorn app:app --host 0.0.0.0 --port $PORT
```

```toml
[metadata]
id = "hop3-tuto-falcon"
version = "1.0.0"
title = "My Falcon Application"

[build]
packages = ["python3", "python3-pip"]

[run]
start = "uvicorn app:app --host 0.0.0.0 --port $PORT"

[env]
PYTHONUNBUFFERED = "1"

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

### Set Environment Variables

```bash
hop3 config set --app hop3-tuto-falcon SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
```

### Deploy

Deploy the application (first deployment creates the app):

```bash
hop3 deploy hop3-tuto-falcon
```

```console
deployed successfully
```

### Set Hostname

Configure the hostname for nginx proxy:

```bash
hop3 config set --app hop3-tuto-falcon HOST_NAME=hop3-tuto-falcon.$HOP3_TEST_DOMAIN
```

### Apply Configuration

Redeploy to apply the hostname configuration:

```bash
hop3 deploy hop3-tuto-falcon
```

```console
deployed successfully
```

### Verify Deployment

```bash
hop3 status --app hop3-tuto-falcon
```

```console
hop3-tuto-falcon
```

```bash
curl -s http://hop3-tuto-falcon.$HOP3_TEST_DOMAIN/up
```

```console
OK
```

View logs:

```bash
hop3 logs --app hop3-tuto-falcon

# Your app will be available at:
# http://hop3-tuto-falcon.your-hop3-server.example.com
```

### Managing Your Application

```bash
# Restart the application
hop3 restart --app hop3-tuto-falcon

# View/set environment variables
hop3 config show --app hop3-tuto-falcon
hop3 config set --app hop3-tuto-falcon NEW_VAR=value

# Scale workers
hop3 ps scale --app hop3-tuto-falcon web=2
```

## Advanced Configuration

### Middleware

```python
import os

class CORSMiddleware:
    def __init__(self):
        # SECURITY: Always specify allowed origins explicitly - never use '*' in production
        self.allowed_origin = os.environ.get('ALLOWED_ORIGIN', '')
        if not self.allowed_origin:
            raise ValueError("ALLOWED_ORIGIN must be set for CORS")

    async def process_response(self, req, resp, resource, req_succeeded):
        resp.set_header('Access-Control-Allow-Origin', self.allowed_origin)

app = falcon.asgi.App(middleware=[CORSMiddleware()])
```

### SQLAlchemy

```python
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession

engine = create_async_engine(os.getenv("DATABASE_URL"))
```

### Hooks

```python
def authorize(req, resp, resource, params):
    token = req.get_header('Authorization')
    if not token:
        raise falcon.HTTPUnauthorized()

@falcon.before(authorize)
class ProtectedResource:
    async def on_get(self, req, resp):
        resp.media = {"secret": "data"}
```

## Example hop3.toml

```toml
[metadata]
id = "hop3-tuto-falcon"
version = "1.0.0"

[build]
[run]
start = "uvicorn app:app --host 0.0.0.0 --port $PORT --workers 2"

[port]
web = 8000

[healthcheck]
path = "/up"

[[provider]]
name = "postgres"
plan = "standard"
```
