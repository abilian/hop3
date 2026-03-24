# Deploying Robyn on Hop3

This guide walks you through deploying a Robyn application on Hop3. Robyn is a super fast async Python web framework with a Rust runtime.

## Prerequisites

Before you begin, ensure you have:

1. **A Hop3 server** - Follow the [Installation Guide](../../get-started/installation.md)
2. **The Hop3 CLI** - Installed on your local machine
3. **Python 3.10+** - Install from [python.org](https://www.python.org/)
4. **Git** - For version control and deployment

Verify your local setup:

```bash
python3 --version
```

## Step 1: Create a New Robyn Application

```bash
mkdir hop3-tuto-robyn && cd hop3-tuto-robyn && python3 -m venv venv
```

Install Robyn:

```bash
. venv/bin/activate && pip install robyn
```

```console
Successfully installed
```

## Step 2: Create the Application

```python
import os
from datetime import datetime

from robyn import Robyn

app = Robyn(__file__)

# In-memory storage
items = {
    1: {"id": 1, "name": "Item 1", "price": 9.99},
    2: {"id": 2, "name": "Item 2", "price": 19.99},
}
next_id = 3

@app.get("/")
async def home(request):
    return f"""
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
                background: linear-gradient(135deg, #f74c00 0%, #ff8c00 100%);
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
            <p>Your Robyn application is running.</p>
            <p>Powered by Rust!</p>
            <p>Current time: {datetime.now().isoformat()}</p>
        </div>
    </body>
    </html>
    """

@app.get("/up")
async def up(request):
    return "OK"

@app.get("/health")
async def health(request):
    return {
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "version": "1.0.0"
    }

@app.get("/api/info")
async def info(request):
    import sys
    return {
        "name": "hop3-tuto-robyn",
        "version": "1.0.0",
        "python_version": sys.version,
        "framework": "Robyn"
    }

@app.get("/api/items")
async def list_items(request):
    return list(items.values())

@app.get("/api/items/:item_id")
async def get_item(request):
    item_id = int(request.path_params["item_id"])
    if item_id not in items:
        return {"error": "Not found"}, 404
    return items[item_id]

@app.post("/api/items")
async def create_item(request):
    global next_id
    data = request.json()
    item = {"id": next_id, "name": data["name"], "price": data["price"]}
    items[next_id] = item
    next_id += 1
    return item, 201

@app.delete("/api/items/:item_id")
async def delete_item(request):
    item_id = int(request.path_params["item_id"])
    if item_id not in items:
        return {"error": "Not found"}, 404
    del items[item_id]
    return "", 204

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.start(host="0.0.0.0", port=port)
```

## Step 3: Create Requirements

```bash
. venv/bin/activate && pip freeze > requirements.txt
```

```bash
cat requirements.txt | grep -i robyn
```

```console
robyn
```

## Step 4: Test the Application

Test that the application starts correctly (skipped in automated tests - Robyn can take time to compile on first run):

```bash
. venv/bin/activate
python app.py &
sleep 5
curl -s http://localhost:8080/health
pkill -f "python app.py" 2>/dev/null || true
```

Verify the application structure:

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
web: python app.py
```

```toml
[metadata]
id = "hop3-tuto-robyn"
version = "1.0.0"
title = "My Robyn Application"

[build]
packages = ["python3", "python3-pip"]

[run]
start = "python app.py"

[env]
PYTHONUNBUFFERED = "1"

[port]
web = 8080

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
hop3 config:set hop3-tuto-robyn SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
```

### Deploy

Deploy the application (first deployment creates the app):

```bash
hop3 deploy hop3-tuto-robyn
```

```console
deployed successfully
```

### Set Hostname

Configure the hostname for nginx proxy:

```bash
hop3 config:set hop3-tuto-robyn HOST_NAME=hop3-tuto-robyn.$HOP3_TEST_DOMAIN
```

### Apply Configuration

Redeploy to apply the hostname configuration:

```bash
hop3 deploy hop3-tuto-robyn
```

```console
deployed successfully
```

### Verify Deployment

```bash
hop3 app:status hop3-tuto-robyn
```

```console
hop3-tuto-robyn
```

```bash
curl -s http://hop3-tuto-robyn.$HOP3_TEST_DOMAIN/up
```

```console
OK
```

View logs:

```bash
hop3 app:logs hop3-tuto-robyn

# Your app will be available at:
# http://hop3-tuto-robyn.your-hop3-server.example.com
```

### Managing Your Application

```bash
# Restart the application
hop3 app:restart hop3-tuto-robyn

# View/set environment variables
hop3 config:show hop3-tuto-robyn
hop3 config:set hop3-tuto-robyn NEW_VAR=value

# Scale workers
hop3 ps:scale hop3-tuto-robyn web=2
```

## Advanced Configuration

### Multi-process Mode

```python
app.start(host="0.0.0.0", port=port, processes=4)
```

### Middleware

```python
@app.before_request()
async def log_request(request):
    print(f"Request: {request.method} {request.url.path}")
    return request

@app.after_request()
async def add_cors(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    return response
```

### WebSockets

```python
from robyn import WebSocket

websocket = WebSocket(app, "/ws")

@websocket.on("message")
async def message(ws, msg):
    await ws.send(f"Echo: {msg}")
```

## Example hop3.toml

```toml
[metadata]
id = "hop3-tuto-robyn"
version = "1.0.0"

[build]
[run]
start = "python app.py"

[port]
web = 8080

[healthcheck]
path = "/up"

[[provider]]
name = "postgres"
plan = "standard"
```
