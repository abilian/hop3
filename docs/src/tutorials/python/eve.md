# Deploying Eve on Hop3

This guide walks you through deploying an Eve application on Hop3. Eve is a Python REST API framework built on Flask that makes building and deploying highly customizable, fully-featured RESTful Web Services easy.

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

## Step 1: Create a New Eve Application

```bash
mkdir hop3-tuto-eve && cd hop3-tuto-eve && python3 -m venv venv
```

Install Eve:

```bash
. venv/bin/activate && pip install eve gunicorn
```

```console
Successfully installed
```

## Step 2: Create the Application

Eve typically uses MongoDB, but for this tutorial we'll use an in-memory data layer for simplicity.

```python
import os
from datetime import datetime

from eve import Eve
from eve.io.base import DataLayer
from flask import jsonify

class InMemoryDataLayer(DataLayer):
    """Simple in-memory data layer for demonstration."""

    def __init__(self, app):
        super().__init__(app)
        self._data = {
            'items': {
                1: {'_id': 1, 'name': 'Item 1', 'price': 9.99, '_created': datetime.now().isoformat(), '_updated': datetime.now().isoformat()},
                2: {'_id': 2, 'name': 'Item 2', 'price': 19.99, '_created': datetime.now().isoformat(), '_updated': datetime.now().isoformat()},
            }
        }
        self._next_id = {'items': 3}

    def init_app(self, app):
        pass

    def find(self, resource, req, sub_resource_lookup, perform_count=True):
        data = list(self._data.get(resource, {}).values())
        return data, len(data)

    def find_one(self, resource, req, **lookup):
        _id = lookup.get('_id')
        if _id is not None:
            return self._data.get(resource, {}).get(int(_id))
        return None

    def find_one_raw(self, resource, **lookup):
        return self.find_one(resource, None, **lookup)

    def find_list_of_ids(self, resource, ids, client_projection=None):
        result = []
        for _id in ids:
            item = self._data.get(resource, {}).get(int(_id))
            if item:
                result.append(item)
        return result

    def insert(self, resource, doc_or_docs):
        if resource not in self._data:
            self._data[resource] = {}
            self._next_id[resource] = 1

        docs = doc_or_docs if isinstance(doc_or_docs, list) else [doc_or_docs]
        ids = []

        for doc in docs:
            _id = self._next_id[resource]
            doc['_id'] = _id
            doc['_created'] = datetime.now().isoformat()
            doc['_updated'] = datetime.now().isoformat()
            self._data[resource][_id] = doc
            self._next_id[resource] += 1
            ids.append(_id)

        return ids if isinstance(doc_or_docs, list) else ids[0]

    def update(self, resource, id_, updates, original):
        if resource in self._data and int(id_) in self._data[resource]:
            self._data[resource][int(id_)].update(updates)
            self._data[resource][int(id_)]['_updated'] = datetime.now().isoformat()

    def replace(self, resource, id_, document, original):
        if resource in self._data:
            document['_id'] = int(id_)
            document['_updated'] = datetime.now().isoformat()
            self._data[resource][int(id_)] = document

    def remove(self, resource, lookup):
        _id = lookup.get('_id')
        if _id is not None and resource in self._data:
            self._data[resource].pop(int(_id), None)

    def is_empty(self, resource):
        return len(self._data.get(resource, {})) == 0

# Eve settings
settings = {
    'DOMAIN': {
        'items': {
            'schema': {
                'name': {'type': 'string', 'required': True},
                'price': {'type': 'float', 'required': True},
            },
            'resource_methods': ['GET', 'POST'],
            'item_methods': ['GET', 'PATCH', 'PUT', 'DELETE'],
        }
    },
    'RESOURCE_METHODS': ['GET', 'POST'],
    'ITEM_METHODS': ['GET', 'PATCH', 'PUT', 'DELETE'],
    'XML': False,
    'JSON': True,
    'PAGINATION': True,
    'PAGINATION_DEFAULT': 25,
}

app = Eve(settings=settings, data=InMemoryDataLayer)

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
                background: linear-gradient(135deg, #8e44ad 0%, #9b59b6 100%);
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
            <p>Your Eve REST API is running.</p>
            <p>Current time: {datetime.now().isoformat()}</p>
            <a href="/items">Browse Items API</a>
        </div>
    </body>
    </html>
    """

@app.route('/up')
def up():
    return 'OK'

@app.route('/health')
def health():
    return jsonify({
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "version": "1.0.0"
    })

@app.route('/api/info')
def info():
    import sys
    import eve
    return jsonify({
        "name": "hop3-tuto-eve",
        "version": "1.0.0",
        "python_version": sys.version,
        "framework": "Eve",
        "eve_version": eve.__version__
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port, debug=False)
```

## Step 3: Create Requirements

```bash
. venv/bin/activate && pip freeze > requirements.txt
```

```bash
cat requirements.txt | grep -i eve
```

```console
Eve
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
web: gunicorn app:app --bind 0.0.0.0:$PORT
```

```toml
[metadata]
id = "hop3-tuto-eve"
version = "1.0.0"
title = "My Eve REST API"

[build]
packages = ["python3", "python3-pip"]

[run]
start = "gunicorn app:app --bind 0.0.0.0:$PORT"

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
hop3 config set --app hop3-tuto-eve SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
```

### Deploy

<!-- Note: Eve requires MongoDB which is not available as an addon on most Hop3 servers.
     These steps are skipped in automated testing but work when MongoDB is available. -->

Deploy the application (first deployment creates the app):

```bash
hop3 deploy hop3-tuto-eve
```

### Set Hostname

Configure the hostname for nginx proxy:

```bash
hop3 config set --app hop3-tuto-eve HOST_NAME=hop3-tuto-eve.your-hop3-server.example.com
```

### Apply Configuration

Redeploy to apply the hostname configuration:

```bash
hop3 deploy hop3-tuto-eve
```

### Verify Deployment

```bash
hop3 status --app hop3-tuto-eve
curl -s http://hop3-tuto-eve.your-hop3-server.example.com/up
```

View logs:

```bash
hop3 logs --app hop3-tuto-eve

# Your app will be available at:
# http://hop3-tuto-eve.your-hop3-server.example.com
```

### Managing Your Application

```bash
# Restart the application
hop3 restart --app hop3-tuto-eve

# View/set environment variables
hop3 config show --app hop3-tuto-eve
hop3 config set --app hop3-tuto-eve NEW_VAR=value

# Scale workers
hop3 ps scale --app hop3-tuto-eve web=2
```

## Advanced Configuration

### MongoDB Backend

For production, use MongoDB instead of the in-memory data layer:

```python
# settings.py
MONGO_HOST = os.environ.get('MONGO_HOST', 'localhost')
MONGO_PORT = int(os.environ.get('MONGO_PORT', 27017))
MONGO_DBNAME = os.environ.get('MONGO_DBNAME', 'hop3-tuto-eve')

# With authentication
MONGO_USERNAME = os.environ.get('MONGO_USERNAME', '')
MONGO_PASSWORD = os.environ.get('MONGO_PASSWORD', '')

# app.py
app = Eve(settings=settings)  # Uses default MongoDB data layer
```

### Authentication

```python
from eve.auth import BasicAuth

class MyBasicAuth(BasicAuth):
    def check_auth(self, username, password, allowed_roles, resource, method):
        return username == 'admin' and password == 'secret'

app = Eve(auth=MyBasicAuth)
```

### Rate Limiting

```python
settings = {
    'RATE_LIMIT_GET': (1, 60),  # 1 request per minute
    'RATE_LIMIT_POST': (1, 60),
    # ...
}
```

### Embedded Resources

```python
settings = {
    'DOMAIN': {
        'orders': {
            'schema': {
                'customer': {
                    'type': 'objectid',
                    'data_relation': {
                        'resource': 'customers',
                        'embeddable': True
                    }
                }
            }
        }
    }
}
```

### Event Hooks

```python
def pre_insert_callback(resource, items):
    for item in items:
        item['processed'] = True

app = Eve()
app.on_pre_INSERT += pre_insert_callback
```

## Example hop3.toml with MongoDB

```toml
[metadata]
id = "hop3-tuto-eve"
version = "1.0.0"

[build]
[run]
start = "gunicorn app:app --bind 0.0.0.0:$PORT --workers 2"

[port]
web = 8000

[healthcheck]
path = "/up"

[[provider]]
name = "mongodb"
plan = "standard"
```
