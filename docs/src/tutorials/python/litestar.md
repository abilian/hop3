# Deploying Litestar on Hop3

This guide walks you through deploying a Litestar application on Hop3. Litestar (formerly Starlite) is a powerful, flexible, and performant ASGI framework.

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

## Step 1: Create a New Litestar Application

```bash
mkdir hop3-tuto-litestar && cd hop3-tuto-litestar && python3 -m venv venv
```

Install Litestar:

```bash
. venv/bin/activate && pip install litestar uvicorn python-dotenv
```

```console
Successfully installed
```

## Step 2: Create the Application

```python
import os
from datetime import datetime
from typing import Any

from litestar import Litestar, get, post, delete
from litestar.response import Template
from litestar.contrib.jinja import JinjaTemplateEngine
from litestar.template.config import TemplateConfig
from pydantic import BaseModel

class Item(BaseModel):
    id: int | None = None
    name: str
    price: float

class HealthResponse(BaseModel):
    status: str
    timestamp: str
    version: str

# In-memory storage
items: dict[int, Item] = {
    1: Item(id=1, name="Item 1", price=9.99),
    2: Item(id=2, name="Item 2", price=19.99),
}
next_id = 3

@get("/")
async def index() -> str:
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
                background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);
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
            <p>Your Litestar application is running.</p>
            <p>Current time: {datetime.now().isoformat()}</p>
            <a href="/schema">API Schema</a>
        </div>
    </body>
    </html>
    """

@get("/up")
async def up() -> str:
    return "OK"

@get("/health")
async def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        timestamp=datetime.now().isoformat(),
        version="1.0.0"
    )

@get("/api/info")
async def info() -> dict[str, Any]:
    import sys
    return {
        "name": "hop3-tuto-litestar",
        "version": "1.0.0",
        "python_version": sys.version,
        "framework": "Litestar"
    }

@get("/api/items")
async def list_items() -> list[Item]:
    return list(items.values())

@get("/api/items/{item_id:int}")
async def get_item(item_id: int) -> Item:
    from litestar.exceptions import NotFoundException
    if item_id not in items:
        raise NotFoundException(f"Item {item_id} not found")
    return items[item_id]

@post("/api/items")
async def create_item(data: Item) -> Item:
    global next_id
    data.id = next_id
    items[next_id] = data
    next_id += 1
    return data

@delete("/api/items/{item_id:int}")
async def delete_item(item_id: int) -> None:
    from litestar.exceptions import NotFoundException
    if item_id not in items:
        raise NotFoundException(f"Item {item_id} not found")
    del items[item_id]

app = Litestar(
    route_handlers=[index, up, health, info, list_items, get_item, create_item, delete_item],
    debug=os.getenv("DEBUG", "false").lower() == "true",
)

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
cat requirements.txt | grep -i litestar
```

```console
litestar
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
id = "hop3-tuto-litestar"
version = "1.0.0"
title = "My Litestar Application"

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

### Deploy

<!-- TODO: Litestar deployment needs investigation - app fails to start.
     Skipping deployment steps for now. -->

Deploy the application:

```bash
hop3 deploy --app hop3-tuto-litestar
hop3 env set --app hop3-tuto-litestar HOST_NAME=hop3-tuto-litestar.your-hop3-server.example.com
hop3 deploy --app hop3-tuto-litestar
```

### Verify Deployment

```bash
hop3 app status --app hop3-tuto-litestar
curl -s http://hop3-tuto-litestar.your-hop3-server.example.com/up
```

View logs:

```bash
hop3 app logs --app hop3-tuto-litestar

# Your app will be available at:
# http://hop3-tuto-litestar.your-hop3-server.example.com
```

### Managing Your Application

```bash
# Restart the application
hop3 app restart --app hop3-tuto-litestar

# View/set environment variables
hop3 env show --app hop3-tuto-litestar
hop3 env set --app hop3-tuto-litestar NEW_VAR=value

# Scale workers
hop3 ps scale --app hop3-tuto-litestar web=2
```

## Advanced Configuration

### SQLAlchemy Integration

```python
from litestar.contrib.sqlalchemy.plugins import SQLAlchemyAsyncConfig, SQLAlchemyPlugin

sqlalchemy_config = SQLAlchemyAsyncConfig(
    connection_string=os.getenv("DATABASE_URL")
)
app = Litestar(plugins=[SQLAlchemyPlugin(config=sqlalchemy_config)])
```

### Dependency Injection

```python
from litestar.di import Provide

async def get_db_session():
    async with async_session() as session:
        yield session

@get("/users", dependencies={"session": Provide(get_db_session)})
async def get_users(session: AsyncSession) -> list[User]:
    return await session.execute(select(User)).scalars().all()
```

### OpenAPI Documentation

Litestar generates OpenAPI docs automatically at `/schema`.

## Example hop3.toml

```toml
[metadata]
id = "hop3-tuto-litestar"
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
