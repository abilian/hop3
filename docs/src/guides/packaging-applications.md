# How to Package Applications for Hop3

This guide provides step-by-step instructions for packaging your applications so they can be deployed and managed by Hop3. Whether you're deploying a Python web app, a Node.js service, a static site, or any other type of application, this guide will show you exactly what files to create and how to structure your project.

## Table of Contents

1. [Understanding Hop3 Application Structure](#understanding-hop3-application-structure)
2. [Quick Start: Minimal Configuration](#quick-start-minimal-configuration)
3. [Configuration Options](#configuration-options)
4. [Complete Examples by Technology](#complete-examples-by-technology)
5. [Advanced Patterns](#advanced-patterns)
6. [Testing Your Package](#testing-your-package)
7. [Troubleshooting](#troubleshooting)

## Understanding Hop3 Application Structure

Hop3 applications require minimal configuration to deploy. At its core, you need:

1. **Your application code** - The actual source files
2. **Dependency declaration** - How to install required packages
3. **Process definition** - How to run your application

Hop3 supports two configuration approaches:

- **Procfile** (convention) - Simple, Heroku-compatible, works out of the box
- **hop3.toml** (configuration) - Advanced, full-featured, optional

You can use either one or both together. When both exist, `hop3.toml` settings override `Procfile` settings.

## Quick Start: Minimal Configuration

### Option 1: Using Procfile Only (Simplest)

For most applications, a simple `Procfile` is all you need.

**Project structure:**
```
my-app/
├── app.py                  # Your application code
├── requirements.txt        # Python dependencies
└── Procfile               # Process definition
```

**Procfile:**
```
web: gunicorn app:app --bind 0.0.0.0:$PORT
```

That's it! Hop3 will:
- Detect it's a Python application (from `requirements.txt`)
- Install dependencies automatically
- Run the command specified in `Procfile`

### Option 2: Using hop3.toml Only (Full Control)

For more control, use `hop3.toml`:

**Project structure:**
```
my-app/
├── app.py
├── requirements.txt
└── hop3.toml
```

**hop3.toml:**
```toml
[metadata]
id = "my-app"
version = "1.0.0"

[run]
start = "gunicorn app:app --bind 0.0.0.0:$PORT"
```

### Option 3: Hybrid Approach (Best of Both)

Use `Procfile` for basics and `hop3.toml` for advanced features:

**Procfile:**
```
web: gunicorn app:app
worker: celery worker
```

**hop3.toml:**
```toml
[metadata]
id = "my-app"

[build]
before-build = "pip install -r requirements-dev.txt"

[[provider]]
name = "postgres"
```

Result:
- `web` and `worker` processes from Procfile
- Build configuration and database from hop3.toml

## Configuration Options

### Procfile Format

The `Procfile` declares process types using the format:

```
<process-type>: <command>
```

**Common process types:**

| Process Type | Purpose | Example |
|-------------|---------|---------|
| `web` | HTTP server (public-facing) | `web: gunicorn app:app` |
| `worker` | Background job processor | `worker: celery worker` |
| `scheduler` | Scheduled tasks | `scheduler: celery beat` |
| `static` | Static file directory | `static: public` |
| `wsgi` | WSGI application | `wsgi: app:application` |

**Special commands:**

| Command | When It Runs | Purpose |
|---------|--------------|---------|
| `prebuild` | Before building | Install build tools, compile assets |
| `build` | During build phase | Build your application |
| `prerun` | Before starting app | Database migrations, setup tasks |

**Example comprehensive Procfile:**
```
prebuild: npm ci
build: npm run build
prerun: python manage.py migrate
web: gunicorn myapp.wsgi:application --workers 4
worker: celery worker --app=myapp
scheduler: celery beat --app=myapp
static: public
```

### hop3.toml Sections

#### `[metadata]` - Application Identity

```toml
[metadata]
id = "my-app"                    # Required: Unique identifier
version = "1.0.0"                # Semantic version
title = "My Application"         # Human-readable name
author = "Your Name <you@example.com>"
description = "A brief description"
```

#### `[build]` - Build Process

```toml
[build]
# Single command
before-build = "npm install"

# Multiple commands (executed with &&)
before-build = ["pip install build-tools", "make setup"]

# Build commands
build = "npm run build"

# System packages needed for build
packages = ["nodejs", "gcc", "make"]

# Python packages for build
pip-install = ["setuptools", "wheel"]

# Run tests after build
test = "npm test"
```

#### `[run]` - Runtime Configuration

```toml
[run]
# Main application command (maps to Procfile "web:")
start = "gunicorn app:app --workers 4"

# Commands before starting (maps to Procfile "prerun:")
before-run = ["python manage.py migrate", "python manage.py collectstatic"]

# System packages needed at runtime
packages = ["postgresql-client", "redis"]
```

#### `[env]` - Environment Variables

```toml
[env]
DEBUG = "false"
DATABASE_URL = "postgresql://localhost/mydb"
LOG_LEVEL = "info"
ALLOWED_HOSTS = "myapp.example.com"
```

**⚠️ Security Note:** Don't hardcode secrets in `hop3.toml`. Use the CLI to set sensitive values:

```bash
hop3 config set --app my-app SECRET_KEY="actual-secret-value"
hop3 config set --app my-app API_TOKEN="sensitive-token"
```

#### `[port]` - Port Configuration

```toml
[port]
web = 8000      # Main web service port
api = 8080      # API service port
metrics = 9090  # Metrics endpoint
```

#### `[healthcheck]` - Health Monitoring

```toml
[healthcheck]
path = "/health/"     # Health check endpoint
timeout = 30          # Request timeout (seconds)
interval = 60         # Check frequency (seconds)
```

#### `[[provider]]` - Service Dependencies

Use double brackets `[[provider]]` for arrays in TOML.

```toml
# PostgreSQL database
[[provider]]
name = "postgres"
plan = "standard"
version = "15"

# Redis cache
[[provider]]
name = "redis"
plan = "basic"
version = "7"
```

## Complete Examples by Technology

### Python: Flask with pip

**Files needed:**
```
flask-app/
├── app.py
├── requirements.txt
└── Procfile
```

**app.py:**
```python
from flask import Flask
import os

app = Flask(__name__)

@app.route('/')
def hello():
    return 'Hello from Flask!'

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
```

**requirements.txt:**
```
flask
gunicorn
```

**Procfile:**
```
web: gunicorn app:app --bind 0.0.0.0:$PORT --workers 2
```

**Deploy:**
```bash
cd flask-app
git init
git add .
git commit -m "Initial commit"
hop3 deploy
```

### Python: Django with Poetry

**Files needed:**
```
django-app/
├── myproject/
│   ├── __init__.py
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
├── manage.py
├── pyproject.toml
└── hop3.toml
```

**pyproject.toml:**
```toml
[tool.poetry]
name = "django-app"
version = "1.0.0"

[tool.poetry.dependencies]
python = "^3.10"
Django = "^4.2"
gunicorn = "^21.0"
psycopg2-binary = "^2.9"

[build-system]
requires = ["poetry-core>=1.0.0"]
build-backend = "poetry.core.masonry.api"
```

**hop3.toml:**
```toml
[metadata]
id = "django-app"
version = "1.0.0"

[build]
# Poetry automatically installs dependencies
before-build = "poetry install --no-dev"

[run]
start = "poetry run gunicorn myproject.wsgi:application --workers 4"
before-run = "poetry run python manage.py migrate --noinput"

[env]
DJANGO_SETTINGS_MODULE = "myproject.settings"
SECRET_KEY = "change-this-in-production"

[[provider]]
name = "postgres"
plan = "standard"
```

**Deploy:**
```bash
cd django-app
git init
git add .
git commit -m "Initial commit"
hop3 config set --app django-app SECRET_KEY="$(openssl rand -hex 32)"
hop3 deploy
```

### Node.js: Express Application

**Files needed:**
```
express-app/
├── app.js
├── package.json
└── Procfile
```

**package.json:**
```json
{
  "name": "express-app",
  "version": "1.0.0",
  "main": "app.js",
  "dependencies": {
    "express": "^4.18.0"
  },
  "scripts": {
    "start": "node app.js"
  }
}
```

**app.js:**
```javascript
const express = require('express');
const app = express();

const port = process.env.PORT || 3000;
const host = process.env.BIND_ADDRESS || '0.0.0.0';

app.get('/', (req, res) => {
  res.send('Hello from Express!');
});

app.listen(port, host, () => {
  console.log(`Server running on ${host}:${port}`);
});
```

**Procfile:**
```
web: node app.js
```

**Deploy:**
```bash
cd express-app
npm install  # Generate package-lock.json
git init
git add .
git commit -m "Initial commit"
hop3 deploy
```

### Node.js: TypeScript Application

**Files needed:**
```
typescript-app/
├── src/
│   └── server.ts
├── package.json
├── tsconfig.json
└── hop3.toml
```

**package.json:**
```json
{
  "name": "typescript-app",
  "version": "1.0.0",
  "scripts": {
    "build": "tsc",
    "start": "node dist/server.js"
  },
  "dependencies": {
    "express": "^4.18.0"
  },
  "devDependencies": {
    "@types/express": "^4.17.0",
    "@types/node": "^20.0.0",
    "typescript": "^5.0.0"
  }
}
```

**tsconfig.json:**
```json
{
  "compilerOptions": {
    "target": "ES2020",
    "module": "commonjs",
    "outDir": "./dist",
    "rootDir": "./src",
    "strict": true
  }
}
```

**hop3.toml:**
```toml
[metadata]
id = "typescript-app"

[build]
before-build = "npm ci"
build = "npm run build"
test = "npm test"

[run]
start = "npm start"
```

### Static Website

**Files needed:**
```
static-site/
├── public/
│   ├── index.html
│   ├── style.css
│   └── script.js
└── Procfile
```

**public/index.html:**
```html
<!DOCTYPE html>
<html>
<head>
    <title>My Static Site</title>
    <link rel="stylesheet" href="style.css">
</head>
<body>
    <h1>Hello from Hop3!</h1>
    <script src="script.js"></script>
</body>
</html>
```

**Procfile:**
```
static: public
```

**Deploy:**
```bash
cd static-site
git init
git add .
git commit -m "Initial commit"
hop3 deploy
```

### Go Application

**Files needed:**
```
go-app/
├── server.go
├── go.mod
└── Procfile
```

**go.mod:**
```go
module myapp

go 1.21

require github.com/gin-gonic/gin v1.9.1
```

**server.go:**
```go
package main

import (
    "fmt"
    "os"
    "github.com/gin-gonic/gin"
)

func main() {
    port := os.Getenv("PORT")
    if port == "" {
        port = "8080"
    }

    r := gin.Default()
    r.GET("/", func(c *gin.Context) {
        c.String(200, "Hello from Go!")
    })

    r.Run(":" + port)
}
```

**Procfile:**
```
web: ./server
```

**hop3.toml:**
```toml
[build]
build = "go build -o server server.go"

[run]
start = "./server"
```

## Advanced Patterns

### Multi-Process Applications

**Procfile:**
```
# Web server
web: gunicorn app:app --workers 4

# Background worker
worker: celery worker --app=myapp --loglevel=info

# Scheduler
scheduler: celery beat --app=myapp --loglevel=info

# Real-time service
realtime: python websocket_server.py
```

Each process type runs independently and scales separately.

### Build-Time vs Runtime Packages

Some packages are only needed during build, others at runtime:

**hop3.toml:**
```toml
[build]
# Build-time packages (compilers, build tools)
packages = ["gcc", "g++", "make", "nodejs"]
pip-install = ["setuptools", "wheel", "cython"]

# Build step
build = "python setup.py build_ext"

[run]
# Runtime packages (minimal set for production)
packages = ["postgresql-client"]

# No build tools needed at runtime
start = "gunicorn app:app"
```

**Benefits:**
- Smaller runtime container
- Faster deployments
- Better security (fewer packages = smaller attack surface)

### Environment-Specific Configuration

**Local .env file** (not committed):
```bash
DEBUG=true
DATABASE_URL=postgresql://localhost/dev_db
```

**Production (via CLI):**
```bash
hop3 config set --app myapp DEBUG=false
hop3 config set --app myapp DATABASE_URL="postgresql://prod-server/prod_db"
hop3 config set --app myapp SECRET_KEY="$(openssl rand -hex 32)"
```

**hop3.toml** (defaults only):
```toml
[env]
# Safe defaults that work everywhere
LOG_LEVEL = "info"
WORKERS = "2"
```

### Database Migrations

**Option 1: Before Run Hook (Recommended)**

**hop3.toml:**
```toml
[run]
before-run = "python manage.py migrate --noinput"
start = "gunicorn app:app"
```

Migrations run automatically before each deployment.

**Option 2: Separate Command**

**Procfile:**
```
release: python manage.py migrate
web: gunicorn app:app
```

**Deploy with migrations:**
```bash
hop3 run myapp release  # Run migrations
hop3 deploy            # Deploy new version
```

### Asset Compilation

**hop3.toml:**
```toml
[build]
before-build = "npm ci"
build = ["npm run build", "python manage.py collectstatic --noinput"]

[run]
start = "gunicorn app:app"
```

**What happens:**
1. Install npm dependencies (`npm ci`)
2. Build frontend assets (`npm run build`)
3. Collect Django static files (`collectstatic`)
4. Start application

### Multi-Stage Builds

**For Node.js applications:**

**hop3.toml:**
```toml
[build]
# Install all dependencies (including dev)
before-build = "npm ci"

# Build production assets
build = "npm run build"

# Prune dev dependencies before deployment
build = ["npm run build", "npm prune --production"]

[run]
start = "node dist/server.js"
```

### Custom Build Scripts

**package.json:**
```json
{
  "scripts": {
    "build": "tsc && webpack --mode production",
    "postbuild": "node scripts/optimize.js"
  }
}
```

**hop3.toml:**
```toml
[build]
before-build = "npm ci"
build = "npm run build"
# npm automatically runs postbuild after build
```

## Testing Your Package

### 1. Test Locally First

**Create local .env file:**
```bash
# .env
PORT=5000
DATABASE_URL=postgresql://localhost/test_db
```

**Run your start command:**
```bash
# Python example
source .env
gunicorn app:app --bind 0.0.0.0:$PORT

# Node.js example
source .env
node app.js
```

**Test in browser:**
```bash
curl http://localhost:5000
```

### 2. Validate Configuration Files

**Check Procfile syntax:**
```bash
# Each line should be: <process-type>: <command>
cat Procfile

# Good:
web: gunicorn app:app

# Bad (missing colon):
web gunicorn app:app
```

**Validate hop3.toml:**
```bash
# Check TOML syntax
cat hop3.toml | python -c "import sys, tomli; tomli.loads(sys.stdin.read())"
```

### 3. Test Deployment in Staging

**Create a test deployment:**
```bash
# Deploy to staging first
hop3 deploy --app myapp-staging

# Test the deployed app
curl https://myapp-staging.hop3.example.com

# Check logs
hop3 logs --app myapp-staging

# Check status
hop3 status --app myapp-staging
```

### 4. Common Issues to Check

**Environment variables:**
```bash
# Verify all required env vars are set
hop3 config show --app myapp

# Add missing vars
hop3 config set --app myapp DATABASE_URL="..."
```

**Port binding:**
```bash
# Your app MUST use the PORT environment variable
# Hop3 sets this automatically

# Good (Python):
port = int(os.environ.get('PORT', 5000))

# Good (Node.js):
const port = process.env.PORT || 3000

# Bad (hardcoded):
app.listen(8000)  # Won't work!
```

**File paths:**
```bash
# Use relative paths, not absolute
# Good:
./manage.py migrate

# Bad:
/home/user/myapp/manage.py migrate
```

## Troubleshooting

### Application Won't Start

**Check logs:**
```bash
hop3 logs myapp --tail 100
```

**Common causes:**

1. **Wrong start command**
   ```bash
   # Verify in Procfile or hop3.toml
   cat Procfile
   ```

2. **Missing dependencies**
   ```bash
   # Check requirements.txt or package.json
   # Redeploy to reinstall
   hop3 deploy
   ```

3. **Port binding issues**
   ```python
   # Make sure you use $PORT
   port = int(os.environ['PORT'])  # Will fail if PORT not set
   port = int(os.environ.get('PORT', 5000))  # Better
   ```

### Build Failures

**Check build logs:**
```bash
hop3 logs myapp --tail 200 | grep -A 10 "BUILD"
```

**Common causes:**

1. **Missing build dependencies**
   ```toml
   [build]
   packages = ["gcc", "python3-dev"]  # Add missing packages
   ```

2. **Build timeout**
   ```toml
   [build]
   # Split long builds into smaller steps
   before-build = "pip install numpy"  # Heavy package first
   build = "pip install -r requirements.txt"
   ```

### Database Connection Errors

**Check DATABASE_URL:**
```bash
hop3 config get --app myapp DATABASE_URL
```

**Verify database service:**
```bash
# List attached services
hop3 addon list --app myapp

# Attach database if missing
hop3 addon create postgres myapp-db
hop3 addon attach myapp-db --app myapp
```

### Static Files Not Serving

**Check static configuration:**
```
# Procfile
static: public

# Or hop3.toml
[run]
static-files = "public"
```

**Verify directory exists:**
```bash
ls -la public/
```

### Permission Errors

**Don't use sudo in commands:**
```toml
# Bad:
start = "sudo gunicorn app:app"

# Good:
start = "gunicorn app:app"
```

### Environment Variable Not Available

**Set via CLI:**
```bash
# Set the variable
hop3 config set --app myapp MY_VAR="value"

# Restart to apply
hop3 restart --app myapp

# Verify
hop3 config show --app myapp
```

## Best Practices Checklist

- [ ] Use `$PORT` environment variable for port binding
- [ ] Never hardcode secrets in `hop3.toml` or `Procfile`
- [ ] Include all dependencies in `requirements.txt` / `package.json`
- [ ] Test locally before deploying
- [ ] Use `before-run` for database migrations
- [ ] Set up health check endpoints
- [ ] Configure automated backups for production
- [ ] Use environment variables for configuration
- [ ] Keep build artifacts out of git (use `.gitignore`)
- [ ] Document required environment variables in README

## Quick Reference

**Minimal Flask App:**
```
app.py + requirements.txt + Procfile
```

**Minimal Node.js App:**
```
app.js + package.json + Procfile
```

**Static Site:**
```
public/index.html + Procfile
```

**With Database:**
```
Add [[provider]] in hop3.toml
```

**With Build Step:**
```
Add [build] section with before-build/build
```

## Next Steps

- [Quickstart Guide](../get-started/quickstart.md) - Deploy your first app
- [hop3.toml Reference](../reference/config.md) - Complete configuration reference
- [Migration Guide](migration-guide.md) - Migrate from other platforms
- [CLI Reference](../reference/cli.md) - All available commands

For help, run:
```bash
hop3 help
hop3 deploy --help
```
