
# Deploying Sanic on Hop3

This guide walks you through deploying a Sanic application on Hop3. Sanic is a Python async web server and framework designed for fast HTTP responses.

## Prerequisites

Before you begin, ensure you have:

1. **A Hop3 server** - Follow the [Installation Guide](../installation.md)
2. **The Hop3 CLI** - Installed on your local machine
3. **Python 3.10+** - Install from [python.org](https://www.python.org/)
4. **Git** - For version control and deployment

Verify your local setup:

```bash
python3 --version
```

```text
Python 3\.[0-9]+\.
```

## Step 1: Create a New Sanic Application

```bash
mkdir hop3-tuto-sanic && cd hop3-tuto-sanic && python3 -m venv venv
```

Install Sanic:

```bash
. venv/bin/activate && pip install sanic
```

```text
Successfully installed
```

## Step 2: Create the Application

```python
import os
from datetime import datetime

from sanic import Sanic
from sanic.response import html, text, json

app = Sanic("hop3-tuto-sanic")

# In-memory storage
items = {
    1: {"id": 1, "name": "Item 1", "price": 9.99},
    2: {"id": 2, "name": "Item 2", "price": 19.99},
}
next_id = 3

@app.get("/")
async def home(request):
    return html(f"""
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
                background: linear-gradient(135deg, #ff0066 0%, #ff6600 100%);
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
            <p>Your Sanic application is running.</p>
            <p>Current time: {datetime.now().isoformat()}</p>
        </div>
    </body>
    </html>
    """)

@app.get("/up")
async def up(request):
    return text("OK")

@app.get("/health")
async def health(request):
    return json({
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "version": "1.0.0"
    })

@app.get("/api/info")
async def info(request):
    import sys
    return json({
        "name": "hop3-tuto-sanic",
        "version": "1.0.0",
        "python_version": sys.version,
        "framework": "Sanic",
        "sanic_version": Sanic.__version__
    })

@app.get("/api/items")
async def list_items(request):
    return json(list(items.values()))

@app.get("/api/items/<item_id:int>")
async def get_item(request, item_id: int):
    if item_id not in items:
        return json({"error": "Not found"}, status=404)
    return json(items[item_id])

@app.post("/api/items")
async def create_item(request):
    global next_id
    data = request.json
    item = {"id": next_id, "name": data["name"], "price": data["price"]}
    items[next_id] = item
    next_id += 1
    return json(item, status=201)

@app.delete("/api/items/<item_id:int>")
async def delete_item(request, item_id: int):
    if item_id not in items:
        return json({"error": "Not found"}, status=404)
    del items[item_id]
    return text("", status=204)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port, access_log=True, auto_reload=False)
```

## Step 3: Create Requirements

```bash
. venv/bin/activate && pip freeze > requirements.txt
```

```bash
cat requirements.txt | grep -i sanic
```

```text
sanic
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

```text
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
web: sanic app:app --host 0.0.0.0 --port $PORT --workers 2
```

```toml
[metadata]
id = "hop3-tuto-sanic"
version = "1.0.0"
title = "My Sanic Application"

[build]
packages = ["python3", "python3-pip"]

[run]
start = "sanic app:app --host 0.0.0.0 --port $PORT --workers 2"

[env]
PYTHONUNBUFFERED = "1"
SANIC_ACCESS_LOG = "true"

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
hop3 config:set hop3-tuto-sanic SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
```

### Deploy

Deploy the application (first deployment creates the app):

```bash
hop3 deploy hop3-tuto-sanic
```

```text
deployed successfully
```

### Set Hostname

Configure the hostname for nginx proxy:

```bash
hop3 config:set hop3-tuto-sanic HOST_NAME=hop3-tuto-sanic.$HOP3_TEST_DOMAIN
```

### Apply Configuration

Redeploy to apply the hostname configuration:

```bash
hop3 deploy hop3-tuto-sanic
```

```text
deployed successfully
```

### Verify Deployment

```bash
hop3 app:status hop3-tuto-sanic
```

```text
hop3-tuto-sanic
```

```bash
curl -s http://hop3-tuto-sanic.$HOP3_TEST_DOMAIN/up
```

```text
OK
```

View logs:

```bash
hop3 app:logs hop3-tuto-sanic

# Your app will be available at:
# http://hop3-tuto-sanic.your-hop3-server.example.com
```

### Managing Your Application

```bash
# Restart the application
hop3 app:restart hop3-tuto-sanic

# View/set environment variables
hop3 config:show hop3-tuto-sanic
hop3 config:set hop3-tuto-sanic NEW_VAR=value

# Scale workers
hop3 ps:scale hop3-tuto-sanic web=2
```

## Advanced Configuration

### Blueprints

```python
from sanic import Blueprint

api = Blueprint("api", url_prefix="/api/v1")

@api.get("/users")
async def get_users(request):
    return json([])

app.blueprint(api)
```

### Middleware

```python
import os

@app.middleware("request")
async def log_request(request):
    print(f"Request: {request.method} {request.path}")

@app.middleware("response")
async def add_cors(request, response):
    # SECURITY: Always specify allowed origins explicitly - never use '*' in production
    allowed_origin = os.environ.get("ALLOWED_ORIGIN", "")
    if allowed_origin:
        response.headers["Access-Control-Allow-Origin"] = allowed_origin
```

### WebSockets

```python
@app.websocket("/ws")
async def feed(request, ws):
    while True:
        data = await ws.recv()
        await ws.send(f"Echo: {data}")
```

## Example hop3.toml

```toml
[metadata]
id = "hop3-tuto-sanic"
version = "1.0.0"

[build]
[run]
start = "sanic app:app --host 0.0.0.0 --port $PORT --workers 2 --fast"

[port]
web = 8000

[healthcheck]
path = "/up"

[[provider]]
name = "postgres"
plan = "standard"
```
