---
tutorial:
  name: fastapi-hop3-tutorial
  env:
    PYTHONDONTWRITEBYTECODE: "1"
    PIP_DISABLE_PIP_VERSION_CHECK: "1"
  teardown:
    - rm -rf hop3-tuto-fastapi venv 2>/dev/null || true
    - hop3 app destroy --app hop3-tuto-fastapi -y 2>/dev/null || true
---

# Deploying FastAPI on Hop3

This guide walks you through deploying a FastAPI application on Hop3. By the end, you'll have a production-ready async Python API with automatic OpenAPI documentation running on your own infrastructure.

## Prerequisites

Before you begin, ensure you have:

1. **A Hop3 server** - Follow the [Installation Guide](../../get-started/server-setup.md) if you haven't set one up yet
2. **The Hop3 CLI** - Installed on your local machine
3. **Python 3.10+** - Install from [python.org](https://www.python.org/) or via your package manager
4. **pip** - Python package manager (comes with Python)
5. **Git** - For version control and deployment

Verify your local setup:

```bash exec id=check-python
python3 --version
```

```output regex
Python 3\.[0-9]+\.
```

```bash exec id=check-pip
pip3 --version
```

```output regex
pip [0-9]+\.
```

## Step 1: Create a New FastAPI Application

Create the project directory and virtual environment:

```bash exec id=create-project
mkdir hop3-tuto-fastapi && cd hop3-tuto-fastapi && python3 -m venv venv
```

```assert file-exists path=hop3-tuto-fastapi/venv/bin/activate
```

Activate the virtual environment and install FastAPI with Uvicorn:

```bash exec id=install-fastapi dir=hop3-tuto-fastapi timeout=60
. venv/bin/activate && pip install fastapi uvicorn[standard] python-dotenv pydantic-settings
```

```output contains
Successfully installed
```

## Step 2: Create the Application

Create the main application file:

```file path=hop3-tuto-fastapi/main.py
import os
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

app = FastAPI(
    title="My FastAPI App",
    description="A FastAPI application deployed on Hop3",
    version="1.0.0",
)


class HealthResponse(BaseModel):
    status: str
    timestamp: str
    version: str


class InfoResponse(BaseModel):
    name: str
    version: str
    python_version: str
    environment: str


class Item(BaseModel):
    name: str
    description: Optional[str] = None
    price: float
    quantity: int = 0


# In-memory storage for demo
items_db: dict[int, Item] = {}
item_counter = 0


@app.get("/", response_class=HTMLResponse)
async def root():
    """Welcome page."""
    return """
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
                background: linear-gradient(135deg, #009688 0%, #4CAF50 100%);
                color: white;
            }
            .container {
                text-align: center;
                padding: 2rem;
            }
            h1 { font-size: 3rem; margin-bottom: 1rem; }
            p { font-size: 1.25rem; opacity: 0.9; }
            a {
                display: inline-block;
                margin-top: 1rem;
                padding: 0.75rem 1.5rem;
                background: rgba(255,255,255,0.2);
                border-radius: 8px;
                color: white;
                text-decoration: none;
            }
            a:hover { background: rgba(255,255,255,0.3); }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Hello from Hop3!</h1>
            <p>Your FastAPI application is running.</p>
            <p>Current time: """ + datetime.now().isoformat() + """</p>
            <a href="/docs">API Documentation</a>
        </div>
    </body>
    </html>
    """


@app.get("/up")
async def up():
    """Health check endpoint for Hop3."""
    return "OK"


@app.get("/health", response_model=HealthResponse)
async def health():
    """Detailed health check."""
    return HealthResponse(
        status="ok",
        timestamp=datetime.now().isoformat(),
        version="1.0.0"
    )


@app.get("/api/info", response_model=InfoResponse)
async def info():
    """API information endpoint."""
    import sys
    return InfoResponse(
        name="hop3-tuto-fastapi",
        version="1.0.0",
        python_version=sys.version,
        environment=os.environ.get("ENVIRONMENT", "production")
    )


# CRUD API example
@app.post("/api/items", status_code=201)
async def create_item(item: Item):
    """Create a new item."""
    global item_counter
    item_counter += 1
    items_db[item_counter] = item
    return {"id": item_counter, **item.model_dump()}


@app.get("/api/items")
async def list_items():
    """List all items."""
    return [{"id": k, **v.model_dump()} for k, v in items_db.items()]


@app.get("/api/items/{item_id}")
async def get_item(item_id: int):
    """Get a specific item."""
    if item_id not in items_db:
        raise HTTPException(status_code=404, detail="Item not found")
    return {"id": item_id, **items_db[item_id].model_dump()}


@app.put("/api/items/{item_id}")
async def update_item(item_id: int, item: Item):
    """Update an item."""
    if item_id not in items_db:
        raise HTTPException(status_code=404, detail="Item not found")
    items_db[item_id] = item
    return {"id": item_id, **item.model_dump()}


@app.delete("/api/items/{item_id}", status_code=204)
async def delete_item(item_id: int):
    """Delete an item."""
    if item_id not in items_db:
        raise HTTPException(status_code=404, detail="Item not found")
    del items_db[item_id]
    return None


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
```

```assert file-exists path=hop3-tuto-fastapi/main.py
```

## Step 3: Create Requirements File

Generate the requirements file:

```bash exec id=freeze-requirements dir=hop3-tuto-fastapi
. venv/bin/activate && pip freeze > requirements.txt
```

```assert file-exists path=hop3-tuto-fastapi/requirements.txt
```

Verify the requirements:

```bash exec id=check-requirements dir=hop3-tuto-fastapi
cat requirements.txt | grep -E "^(fastapi|uvicorn)" | head -2
```

```output contains
fastapi
```

```output contains
uvicorn
```

## Step 4: Add Configuration

Create a configuration module using Pydantic settings:

```file path=hop3-tuto-fastapi/config.py
import os
from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings."""

    # Application
    app_name: str = "hop3-tuto-fastapi"
    debug: bool = False
    environment: str = "production"

    # Security - SECRET_KEY must be set in production (no default)
    secret_key: str = ""

    # Database
    database_url: str = "sqlite:///./app.db"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
```

Create an example `.env` file:

```file path=hop3-tuto-fastapi/.env.example
APP_NAME=hop3-tuto-fastapi
DEBUG=false
ENVIRONMENT=production
SECRET_KEY=your-secret-key-here
DATABASE_URL=postgresql://user:pass@localhost:5432/hop3-tuto-fastapi
REDIS_URL=redis://localhost:6379/0
```

## Step 5: Verify the Application Works

Test that the application starts correctly:

Test locally (skipped in automated tests - local server tests are flaky):

```bash skip
. venv/bin/activate && uvicorn main:app --host 0.0.0.0 --port 8000 &
sleep 2
curl -s http://localhost:8000/health
curl -s http://localhost:8000/docs
```

Verify the project structure:

```bash exec id=verify-structure dir=hop3-tuto-fastapi
ls -la *.py requirements.txt
```

```output contains
main.py
```

```output contains
requirements.txt
```

## Step 6: Create Deployment Configuration

### Create a Procfile

Create a `Procfile` in your project root:

```file path=hop3-tuto-fastapi/Procfile
# Main web process (using Uvicorn)
web: uvicorn main:app --host 0.0.0.0 --port $PORT --workers 2
```

### Create hop3.toml

Create a `hop3.toml` for advanced configuration:

```file path=hop3-tuto-fastapi/hop3.toml
[metadata]
id = "hop3-tuto-fastapi"
version = "1.0.0"
title = "My FastAPI Application"

[build]
packages = ["python3", "python3-pip", "python3-venv"]

[run]
start = "uvicorn main:app --host 0.0.0.0 --port $PORT --workers 2"

[env]
ENVIRONMENT = "production"
PYTHONUNBUFFERED = "1"

[port]
web = 8000

[healthcheck]
path = "/up"
timeout = 30
interval = 60
```

Verify the deployment files exist:

```bash exec id=verify-deploy-files dir=hop3-tuto-fastapi
ls -la Procfile hop3.toml
```

```output contains
Procfile
```

```output contains
hop3.toml
```

## Step 7: Initialize Git Repository

Create a `.gitignore` file:

```file path=hop3-tuto-fastapi/.gitignore
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

```bash exec id=git-init dir=hop3-tuto-fastapi
git init
```

```output contains
Initialized empty Git repository
```

```bash exec id=git-add dir=hop3-tuto-fastapi
git add .
```

```bash exec id=git-commit dir=hop3-tuto-fastapi
git commit -m "Initial FastAPI application"
```

```output contains
Initial FastAPI application
```

## Step 8: Deploy to Hop3

The following steps require a Hop3 server. Set the `HOP3_SERVER` environment variable to your server address before running these commands.

### Configure the CLI

If this is your first deployment, initialize Hop3:

```bash skip
hop3 init --ssh root@your-server.example.com
```

### Set Environment Variables

```bash skip
# Generate and set the secret key
hop3 config set --app hop3-tuto-fastapi SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")

# Set environment
hop3 config set --app hop3-tuto-fastapi ENVIRONMENT=production
```

### Deploy

Deploy the application (first deployment creates the app):

```bash exec id=deploy dir=hop3-tuto-fastapi timeout=120
hop3 deploy hop3-tuto-fastapi
```

### Set Hostname

Configure the hostname for nginx proxy:

```bash exec id=set-hostname timeout=30
hop3 config set --app hop3-tuto-fastapi HOST_NAME=hop3-tuto-fastapi.$HOP3_TEST_DOMAIN
```

### Apply Configuration

Redeploy to apply the hostname configuration:

```bash exec id=redeploy dir=hop3-tuto-fastapi timeout=120
hop3 deploy hop3-tuto-fastapi
```

Wait for the application to start:

```bash exec id=wait-for-app timeout=10
sleep 5
```

## Step 9: Verify Deployment

Check your application status:

```bash exec id=check-status timeout=30
hop3 status --app hop3-tuto-fastapi
```

```output contains
hop3-tuto-fastapi
```

```bash exec id=check-health timeout=30
curl -s http://hop3-tuto-fastapi.$HOP3_TEST_DOMAIN/up
```

```output contains
OK
```

View logs:

```bash skip
hop3 logs --app hop3-tuto-fastapi
```

Open your application:

```bash skip
# Your app will be available at:
# http://hop3-tuto-fastapi.your-hop3-server.example.com

# API documentation at:
# http://hop3-tuto-fastapi.your-hop3-server.example.com/docs
```

## Managing Your Application

### Restart the Application

```bash skip
hop3 restart --app hop3-tuto-fastapi
```

### Run Commands in the Application Context

```bash skip
hop3 run hop3-tuto-fastapi python -c "from config import get_settings; print(get_settings())"
```

### View and Manage Environment Variables

```bash skip
# List all variables
hop3 config show --app hop3-tuto-fastapi

# Set a variable
hop3 config set --app hop3-tuto-fastapi NEW_VARIABLE=value

# Remove a variable
hop3 config unset --app hop3-tuto-fastapi OLD_VARIABLE
```

### Scaling

```bash skip
# Check current processes
hop3 ps hop3-tuto-fastapi

# Scale web workers
hop3 ps scale --app hop3-tuto-fastapi web=2
```

## Advanced Configuration

### Adding a Database (PostgreSQL with SQLAlchemy)

Install SQLAlchemy and async PostgreSQL driver:

```bash skip
pip install sqlalchemy[asyncio] asyncpg
pip freeze > requirements.txt
```

Create database models:

```python
# models.py
from sqlalchemy import Column, Integer, String, Float
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import declarative_base, sessionmaker
from config import get_settings

settings = get_settings()

# Convert postgres:// to postgresql+asyncpg://
database_url = settings.database_url
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql+asyncpg://", 1)
elif database_url.startswith("postgresql://"):
    database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)

engine = create_async_engine(database_url, echo=settings.debug)
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

Base = declarative_base()


class Item(Base):
    __tablename__ = "items"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    description = Column(String, nullable=True)
    price = Column(Float)
    quantity = Column(Integer, default=0)


async def get_db():
    async with async_session() as session:
        yield session
```

Add database dependency to routes:

```python
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from models import get_db, Item

@app.get("/api/items")
async def list_items(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Item))
    return result.scalars().all()
```

Create and attach database:

```bash skip
hop3 addons create postgres hop3-tuto-fastapi-db
hop3 addons attach hop3-tuto-fastapi hop3-tuto-fastapi-db
```

### Adding Redis for Caching

Install Redis client:

```bash skip
pip install redis
```

Create a caching utility:

```python
# cache.py
import json
from typing import Optional
import redis.asyncio as redis
from config import get_settings

settings = get_settings()
redis_client = redis.from_url(settings.redis_url)


async def get_cache(key: str) -> Optional[dict]:
    data = await redis_client.get(key)
    if data:
        return json.loads(data)
    return None


async def set_cache(key: str, value: dict, expire: int = 300):
    await redis_client.set(key, json.dumps(value), ex=expire)


async def delete_cache(key: str):
    await redis_client.delete(key)
```

Attach Redis:

```bash skip
hop3 addons create redis hop3-tuto-fastapi-redis
hop3 addons attach hop3-tuto-fastapi hop3-tuto-fastapi-redis
```

### Background Tasks with Celery

Install Celery:

```bash skip
pip install celery[redis]
```

Create Celery configuration:

```python
# tasks.py
from celery import Celery
from config import get_settings

settings = get_settings()

celery_app = Celery(
    "tasks",
    broker=settings.redis_url,
    backend=settings.redis_url
)


@celery_app.task
def process_item(item_id: int):
    # Process item asynchronously
    pass
```

Use in routes:

```python
from tasks import process_item

@app.post("/api/items/{item_id}/process")
async def trigger_process(item_id: int):
    process_item.delay(item_id)
    return {"status": "processing"}
```

Add worker to `Procfile`:

```procfile
web: uvicorn main:app --host 0.0.0.0 --port $PORT
worker: celery -A tasks worker --loglevel=info
```

### Background Tasks (Built-in)

FastAPI has built-in background tasks for simpler use cases:

```python
from fastapi import BackgroundTasks

def send_email(email: str, message: str):
    # Send email (blocking operation)
    pass

@app.post("/api/notify")
async def notify(email: str, background_tasks: BackgroundTasks):
    background_tasks.add_task(send_email, email, "Hello!")
    return {"status": "notification queued"}
```

### Authentication with JWT

Install JWT library:

```bash skip
pip install python-jose[cryptography] passlib[bcrypt]
```

Create authentication:

```python
# auth.py
from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from config import get_settings

settings = get_settings()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=15))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.secret_key, algorithm="HS256")


async def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
    )
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    return username
```

### CORS Configuration

```python
from fastapi.middleware.cors import CORSMiddleware

# SECURITY: Always specify allowed origins explicitly - never use '*' in production
allowed_origins = os.environ.get("ALLOWED_ORIGINS")
if not allowed_origins:
    raise ValueError("ALLOWED_ORIGINS must be set (e.g., 'https://example.com')")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### Request Logging

```python
import logging
import time
from fastapi import Request

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    logger.info(f"{request.method} {request.url.path} - {response.status_code} - {process_time:.3f}s")
    return response
```

## Troubleshooting

### Application Won't Start

Check the logs for errors:

```bash skip
hop3 logs --app hop3-tuto-fastapi --tail
```

Common issues:
- **Missing SECRET_KEY**: Set it with `hop3 config set`
- **Module not found**: Ensure all dependencies are in `requirements.txt`
- **Port binding**: Ensure Uvicorn binds to `0.0.0.0:$PORT`

### Database Connection Issues

Verify the database is attached:

```bash skip
hop3 config show --app hop3-tuto-fastapi | grep DATABASE
```

For async connections, ensure you're using `asyncpg`:

```python
# Convert URL format
database_url = database_url.replace("postgres://", "postgresql+asyncpg://")
```

### Slow Startup

FastAPI with Uvicorn can have slow cold starts with many dependencies:

- Use `--workers` to keep processes warm
- Consider using Gunicorn with Uvicorn workers for better process management:

```procfile
web: gunicorn main:app --bind 0.0.0.0:$PORT --workers 2 --worker-class uvicorn.workers.UvicornWorker
```

### OpenAPI Documentation Issues

If `/docs` doesn't load:

- Check that `fastapi` is properly installed
- Verify no middleware is blocking the routes
- Check logs for any startup errors

## Next Steps

- **[CLI Reference](../../reference/cli.md)** - Complete command reference
- **[hop3.toml Reference](../../reference/config.md)** - Full configuration options
- **[Backup and Restore Guide](../../guides/backup-restore.md)** - Protect your data

## Example Files

### Complete hop3.toml for FastAPI

```toml
# hop3.toml - FastAPI Application

[metadata]
id = "hop3-tuto-fastapi"
version = "1.0.0"
title = "My FastAPI Application"
author = "Your Name <you@example.com>"

[build]
packages = ["python3", "python3-pip", "libpq-dev"]

[run]
start = "uvicorn main:app --host 0.0.0.0 --port $PORT --workers 2"
before-run = "alembic upgrade head"

[env]
ENVIRONMENT = "production"
PYTHONUNBUFFERED = "1"

[port]
web = 8000

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

### Complete Procfile for FastAPI

```procfile
# Procfile - FastAPI Application

# Build phase
# Pre-run hooks (database migrations)
prerun: alembic upgrade head

# Web server
web: uvicorn main:app --host 0.0.0.0 --port $PORT --workers 2

# Alternative: Gunicorn with Uvicorn workers
# web: gunicorn main:app --bind 0.0.0.0:$PORT --workers 2 --worker-class uvicorn.workers.UvicornWorker

# Background worker (optional)
worker: celery -A tasks worker --loglevel=info

# Beat scheduler (optional)
beat: celery -A tasks beat --loglevel=info
```
