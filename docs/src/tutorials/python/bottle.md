# Deploying Bottle on Hop3

This guide walks you through deploying a Bottle application on Hop3. Bottle is a fast, simple micro-framework for small web applications.

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

## Step 1: Create a New Bottle Application

```bash
mkdir hop3-tuto-bottle && cd hop3-tuto-bottle && python3 -m venv venv
```

Install Bottle:

```bash
. venv/bin/activate && pip install bottle gunicorn
```

```console
Successfully installed
```

## Step 2: Create the Application

```python
import os
import json
from datetime import datetime

from bottle import Bottle, request, response, run

app = Bottle()

# In-memory storage
items = {
    1: {"id": 1, "name": "Item 1", "price": 9.99},
    2: {"id": 2, "name": "Item 2", "price": 19.99},
}
next_id = 3

@app.route('/')
def home():
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
                background: linear-gradient(135deg, #2d3436 0%, #636e72 100%);
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
            <p>Your Bottle application is running.</p>
            <p>Current time: {datetime.now().isoformat()}</p>
        </div>
    </body>
    </html>
    """

@app.route('/up')
def up():
    return 'OK'

@app.route('/health')
def health():
    response.content_type = 'application/json'
    return json.dumps({
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "version": "1.0.0"
    })

@app.route('/api/info')
def info():
    import sys
    response.content_type = 'application/json'
    return json.dumps({
        "name": "hop3-tuto-bottle",
        "version": "1.0.0",
        "python_version": sys.version,
        "framework": "Bottle"
    })

@app.route('/api/items')
def list_items():
    response.content_type = 'application/json'
    return json.dumps(list(items.values()))

@app.route('/api/items/<item_id:int>')
def get_item(item_id):
    response.content_type = 'application/json'
    if item_id not in items:
        response.status = 404
        return json.dumps({"error": "Not found"})
    return json.dumps(items[item_id])

@app.route('/api/items', method='POST')
def create_item():
    global next_id
    response.content_type = 'application/json'
    data = request.json
    item = {"id": next_id, "name": data["name"], "price": data["price"]}
    items[next_id] = item
    next_id += 1
    response.status = 201
    return json.dumps(item)

@app.route('/api/items/<item_id:int>', method='DELETE')
def delete_item(item_id):
    if item_id not in items:
        response.status = 404
        return json.dumps({"error": "Not found"})
    del items[item_id]
    response.status = 204
    return ''

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    run(app, host='0.0.0.0', port=port)
```

## Step 3: Create Requirements

```bash
. venv/bin/activate && pip freeze > requirements.txt
```

```bash
cat requirements.txt | grep -i bottle
```

```console
bottle
```

## Step 4: Test the Application

Start the server with a timeout and test it:

```bash
. venv/bin/activate
# Use a random port to avoid conflicts with other tests
export PORT=$((10000 + RANDOM % 50000))
python app.py &
PID=$!
sleep 3
curl -s http://localhost:$PORT/health || echo "Server not responding"
kill $PID 2>/dev/null || true
```

```console
status
```

## Step 5: Create Deployment Configuration

```text
venv/
__pycache__/
*.pyc
.env
```

```procfile
web: gunicorn app:app --bind 0.0.0.0:$PORT
```

```toml
[metadata]
id = "hop3-tuto-bottle"
version = "1.0.0"
title = "Hop3 Tutorial - Bottle"

[build]
packages = ["python3", "python3-pip"]

[run]
start = "gunicorn app:app --bind 0.0.0.0:$PORT"

[env]
PYTHONUNBUFFERED = "1"

[port]
web = 8080

[healthcheck]
path = "/up"
timeout = 30
interval = 60
```

## Step 6: Deploy to Hop3

### Initialize (First Time Only)

```bash
hop3 init --ssh root@your-server.example.com
```

### Deploy

Deploy the application (first deployment creates the app):

```bash
hop3 deploy --app hop3-tuto-bottle
```

```console
deployed successfully
```

### Set Hostname

Configure the hostname for nginx proxy:

```bash
hop3 env set --app hop3-tuto-bottle HOST_NAME=hop3-tuto-bottle.$HOP3_TEST_DOMAIN
```

### Apply Configuration

Redeploy to apply the hostname configuration:

```bash
hop3 deploy --app hop3-tuto-bottle
```

```console
deployed successfully
```

### Verify Deployment

```bash
hop3 app status --app hop3-tuto-bottle
```

```console
hop3-tuto-bottle
```

```bash
curl -s http://hop3-tuto-bottle.$HOP3_TEST_DOMAIN/up
```

```console
OK
```

## Managing Your Application

```bash
# Restart the application
hop3 app restart --app hop3-tuto-bottle

# View logs
hop3 app logs --app hop3-tuto-bottle

# View/set environment variables
hop3 env show --app hop3-tuto-bottle
hop3 env set --app hop3-tuto-bottle NEW_VAR=value

# Scale workers
hop3 ps scale --app hop3-tuto-bottle web=2
```

## Example hop3.toml

```toml
[metadata]
id = "hop3-tuto-bottle"
version = "1.0.0"

[build]
[run]
start = "gunicorn app:app --bind 0.0.0.0:$PORT --workers 2"

[port]
web = 8080

[healthcheck]
path = "/up"
```
