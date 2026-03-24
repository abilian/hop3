# Deploying Starlette on Hop3

This guide walks you through deploying a Starlette application on Hop3. Starlette is a lightweight ASGI framework that powers FastAPI.

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

## Step 1: Create a New Starlette Application

```bash
mkdir hop3-tuto-starlette && cd hop3-tuto-starlette && python3 -m venv venv
```

Install Starlette:

```bash
. venv/bin/activate && pip install starlette uvicorn python-dotenv
```

```console
Successfully installed
```

## Step 2: Create the Application

```python
import os
import json
from datetime import datetime

from starlette.applications import Starlette
from starlette.responses import HTMLResponse, JSONResponse, PlainTextResponse
from starlette.routing import Route

# In-memory storage
items = {
    1: {"id": 1, "name": "Item 1", "price": 9.99},
    2: {"id": 2, "name": "Item 2", "price": 19.99},
}
next_id = 3

async def homepage(request):
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
                background: linear-gradient(135deg, #059669 0%, #10b981 100%);
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
            <p>Your Starlette application is running.</p>
            <p>Current time: {datetime.now().isoformat()}</p>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(html)

async def up(request):
    return PlainTextResponse("OK")

async def health(request):
    return JSONResponse({
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "version": "1.0.0"
    })

async def info(request):
    import sys
    return JSONResponse({
        "name": "hop3-tuto-starlette",
        "version": "1.0.0",
        "python_version": sys.version,
        "framework": "Starlette"
    })

async def list_items(request):
    return JSONResponse(list(items.values()))

async def get_item(request):
    item_id = int(request.path_params["item_id"])
    if item_id not in items:
        return JSONResponse({"error": "Not found"}, status_code=404)
    return JSONResponse(items[item_id])

async def create_item(request):
    global next_id
    data = await request.json()
    item = {"id": next_id, "name": data["name"], "price": data["price"]}
    items[next_id] = item
    next_id += 1
    return JSONResponse(item, status_code=201)

async def delete_item(request):
    item_id = int(request.path_params["item_id"])
    if item_id not in items:
        return JSONResponse({"error": "Not found"}, status_code=404)
    del items[item_id]
    return PlainTextResponse("", status_code=204)

routes = [
    Route("/", homepage),
    Route("/up", up),
    Route("/health", health),
    Route("/api/info", info),
    Route("/api/items", list_items, methods=["GET"]),
    Route("/api/items", create_item, methods=["POST"]),
    Route("/api/items/{item_id:int}", get_item, methods=["GET"]),
    Route("/api/items/{item_id:int}", delete_item, methods=["DELETE"]),
]

app = Starlette(debug=os.getenv("DEBUG", "false").lower() == "true", routes=routes)

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
```

## Step 3: Create Requirements

```bash
. venv/bin/activate && pip freeze > requirements.txt
```

```bash
cat requirements.txt | grep -i starlette
```

```console
starlette
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
id = "hop3-tuto-starlette"
version = "1.0.0"
title = "My Starlette Application"

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
hop3 config:set hop3-tuto-starlette SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
```

### Deploy

Deploy the application (first deployment creates the app):

```bash
hop3 deploy hop3-tuto-starlette
```

```console
deployed successfully
```

### Set Hostname

Configure the hostname for nginx proxy:

```bash
hop3 config:set hop3-tuto-starlette HOST_NAME=hop3-tuto-starlette.$HOP3_TEST_DOMAIN
```

### Apply Configuration

Redeploy to apply the hostname configuration:

```bash
hop3 deploy hop3-tuto-starlette
```

```console
deployed successfully
```

### Verify Deployment

```bash
hop3 app:status hop3-tuto-starlette
```

```console
hop3-tuto-starlette
```

```bash
curl -s http://hop3-tuto-starlette.$HOP3_TEST_DOMAIN/up
```

```console
OK
```

View logs:

```bash
hop3 app:logs hop3-tuto-starlette

# Your app will be available at:
# http://hop3-tuto-starlette.your-hop3-server.example.com
```

### Managing Your Application

```bash
# Restart the application
hop3 app:restart hop3-tuto-starlette

# View/set environment variables
hop3 config:show hop3-tuto-starlette
hop3 config:set hop3-tuto-starlette NEW_VAR=value

# Scale workers
hop3 ps:scale hop3-tuto-starlette web=2
```

## Advanced Configuration

### Middleware

```python
import os
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware

# SECURITY: Always specify allowed origins explicitly - never use '*' in production
allowed_origins = os.environ.get("ALLOWED_ORIGINS")
if not allowed_origins:
    raise ValueError("ALLOWED_ORIGINS must be set (e.g., 'https://example.com')")

middleware = [
    Middleware(CORSMiddleware, allow_origins=allowed_origins.split(","))
]

app = Starlette(routes=routes, middleware=middleware)
```

### Database with encode/databases

```python
from databases import Database

database = Database(os.getenv("DATABASE_URL"))

@app.on_event("startup")
async def startup():
    await database.connect()

@app.on_event("shutdown")
async def shutdown():
    await database.disconnect()
```

### WebSocket Support

```python
from starlette.websockets import WebSocket
from starlette.routing import WebSocketRoute

async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    while True:
        data = await websocket.receive_text()
        await websocket.send_text(f"Echo: {data}")

routes = [
    WebSocketRoute("/ws", websocket_endpoint),
]
```

## Example hop3.toml

```toml
[metadata]
id = "hop3-tuto-starlette"
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
