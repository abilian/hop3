# Native Apps Deployment Caveats

This document captures lessons learned while debugging native (non-Docker) application deployments on Hop3. These caveats apply to apps deployed using `builder = "local"` in their `hop3.toml`.

## Table of Contents

1. [hop3.toml Configuration](#hop3toml-configuration)
2. [PHP/Laravel Applications](#phplaravel-applications)
3. [Database Considerations](#database-considerations)
4. [Test Script Behavior](#test-script-behavior)
5. [Common Pitfalls](#common-pitfalls)

---

## hop3.toml Configuration

### Always Specify `builder = "local"` for Native Apps

Native applications **must** explicitly set the builder in their `hop3.toml`:

```toml
[build]
builder = "local"
toolchain = "php"  # or "node", "python", etc.
```

**Why this matters:**
- The test script (`apps/ngi-apps/test-script.py`) uses the `builder` setting to determine deployment type
- Without `builder = "local"`, apps default to Docker deployment detection
- This causes incorrect status checks and debug info collection (looking for Docker containers that don't exist)

### Toolchain Specification

While optional, explicitly specifying the toolchain helps with build detection:

```toml
[build]
builder = "local"
toolchain = "php"      # For PHP apps
toolchain = "node"     # For Node.js apps
toolchain = "python"   # For Python apps
```

---

## PHP/Laravel Applications

### Laravel's Development Server (`php artisan serve`)

Laravel's built-in development server has a **file watcher** that automatically restarts when it detects file changes. This causes problems in production-like deployments:

#### Problem: Constant 503 Errors

Symptoms:
- App reports as "RUNNING" but returns HTTP 503
- Logs show: `INFO  Environment modified. Restarting server...`
- HTTP checks intermittently fail during restarts

#### Solution: Disable the File Watcher

Add `--no-reload` flag to the serve command:

```toml
[run]
start = "php artisan serve --host=0.0.0.0 --port=${PORT:-8080} --no-reload"
```

### Laravel .env File Handling

Laravel requires specific setup order for the `.env` file:

#### 1. Create .env Before Running Artisan Commands

Many `php artisan` commands require a valid `.env` file. Create a minimal one first:

```bash
# Create minimal .env for artisan to work
if [ ! -f .env ]; then
    echo "APP_KEY=" > .env
fi

# Then generate the key
APP_KEY=$(php artisan key:generate --show 2>/dev/null || echo "base64:$(head -c 32 /dev/urandom | base64)")
```

#### 2. Avoid Cache Commands with `php artisan serve`

**Do NOT run these commands** when using `php artisan serve`:

```bash
# These trigger file watcher restarts!
php artisan config:cache   # Creates bootstrap/cache/config.php
php artisan route:cache    # Creates bootstrap/cache/routes-v7.php
php artisan view:cache     # Compiles views
```

These commands create/modify files that Laravel's file watcher detects, causing restart loops.

#### 3. Essential .env Variables for Laravel

```bash
cat > .env << EOF
APP_KEY=${APP_KEY}
APP_URL=${APP_URL:-http://localhost:${PORT:-8080}}
APP_ENV=production
APP_DEBUG=false

DB_CONNECTION=mysql
DB_HOST=${MYSQL_HOST:-localhost}
DB_PORT=${MYSQL_PORT:-3306}
DB_DATABASE=${MYSQL_DATABASE:-myapp}
DB_USERNAME=${MYSQL_USER:-myapp}
DB_PASSWORD=${MYSQL_PASSWORD:-}

# Disable features that need additional setup
MAIL_MAILER=log
QUEUE_CONNECTION=sync
EOF
```

### PHP Built-in Server

For simpler PHP apps (not Laravel), use PHP's built-in server:

```toml
[run]
start = "php -S 0.0.0.0:${PORT:-8080}"
```

Or with a specific document root:

```toml
[run]
start = "php -S 0.0.0.0:${PORT:-8080} -t public"
```

---

## Database Considerations

### SQLite Concurrency Issues

When running multiple deployments in sequence, SQLite can encounter locking issues:

#### Symptoms

```
(sqlite3.OperationalError) database is locked
IllegalStateChangeError: Method 'close()' can't be called here
```

#### Solutions (Implemented in hop3-server)

1. **WAL Mode**: Enables concurrent reads during writes
2. **Busy Timeout**: Wait instead of failing immediately (30 seconds)
3. **Single Connection Pool**: Prevents concurrent write attempts

These are configured automatically in `hop3/orm/session.py`.

### MySQL Addon Integration

When using MySQL addons, ensure your app reads the correct environment variables:

| Hop3 Variable | Common App Variable |
|---------------|---------------------|
| `MYSQL_HOST` | `DB_HOST` |
| `MYSQL_PORT` | `DB_PORT` |
| `MYSQL_DATABASE` | `DB_DATABASE` |
| `MYSQL_USER` | `DB_USERNAME` |
| `MYSQL_PASSWORD` | `DB_PASSWORD` |
| `DATABASE_URL` | Full connection URL |

Map them in your setup script if needed:

```bash
DB_HOST=${MYSQL_HOST:-localhost}
DB_DATABASE=${MYSQL_DATABASE:-myapp}
```

---

## Test Script Behavior

### Deployment Type Detection

The test script (`apps/ngi-apps/test-script.py`) determines deployment type from `hop3.toml`:

```python
builder = build_config.get("builder", "")
deployment_type = "native" if builder == "local" else "docker"
```

This affects:
- Which status checks are performed (uWSGI vs Docker container)
- Which debug info is collected
- How ports are discovered

### HTTP Health Checks

The test script performs HTTP health checks with retry logic:

- Accepts: 200, 301, 302, 401, 403 as "healthy"
- Treats: 500, 502, 503 as "still starting" (retries)
- Default timeout: 30 seconds for startup, 15 seconds for final check

If your app needs longer startup time, it may fail the health check even when working.

### Debug Info Collection

For native apps, debug info includes:
- uWSGI config (`/home/hop3/uwsgi-enabled/{app}_web.1.ini`)
- App logs (`/home/hop3/apps/{app}/log/web.1.log`)
- Process status (`pgrep -f 'apps/{app}'`)
- Environment variables (`LIVE_ENV` file)
- Source directory contents

---

## Common Pitfalls

### 1. Missing `builder = "local"`

**Symptom**: Test shows "Container not found" for a native app

**Fix**: Add to `hop3.toml`:
```toml
[build]
builder = "local"
```

### 2. App Returns 503 During Startup

**Symptom**: Intermittent 503 errors, logs show restarts

**Causes**:
- Laravel file watcher detecting changes
- App not fully initialized
- Database migrations still running

**Fixes**:
- Add `--no-reload` for Laravel
- Increase startup timeout
- Ensure setup scripts complete before server starts

### 3. Database Connection Failures

**Symptom**: App starts but returns 500, logs show database errors

**Causes**:
- Wrong environment variable names
- Database not ready when app starts
- Missing migrations

**Fixes**:
- Map environment variables correctly in setup script
- Run `php artisan migrate --force` in `before-run`
- Check database addon is provisioned

### 4. Missing Dependencies After Deploy

**Symptom**: App fails with "module not found" or similar

**Causes**:
- `composer install` or `npm install` not in build step
- Wrong working directory

**Fix**: Ensure build commands are in `hop3.toml`:
```toml
[build]
build = "composer install --no-dev --optimize-autoloader"
```

### 5. Port Binding Issues

**Symptom**: App doesn't respond on expected port

**Causes**:
- Hardcoded port instead of using `${PORT}`
- Binding to wrong interface (127.0.0.1 vs 0.0.0.0)

**Fix**: Always use the PORT environment variable:
```toml
[run]
start = "php -S 0.0.0.0:${PORT:-8080}"
```

---

## Recommended hop3.toml Template for PHP Apps

```toml
# Hop3 Configuration for [App Name]

[metadata]
id = "myapp"
version = "1.0.0"
title = "My Application"
description = "Description here"

[build]
# Force local builder for native PHP deployment
builder = "local"
toolchain = "php"

# Download/prepare source
before-build = "bash scripts/download.sh"

# Install dependencies
build = "composer install --no-dev --optimize-autoloader"

[run]
# Setup before starting (create config, run migrations)
before-run = "bash scripts/setup-config.sh"

# Start the application (use --no-reload for Laravel)
start = "php artisan serve --host=0.0.0.0 --port=${PORT:-8080} --no-reload"

[[addons]]
type = "mysql"

[env]
APP_ENV = "production"

[healthcheck]
path = "/"
```

---

## Debugging Checklist

When a native app fails to deploy or start:

1. **Check hop3.toml has `builder = "local"`**
2. **Check logs**: `tail -f /home/hop3/apps/{app}/log/web.1.log`
3. **Check process is running**: `pgrep -f 'apps/{app}'`
4. **Check port binding**: `curl http://127.0.0.1:{port}/`
5. **Check environment**: `cat /home/hop3/apps/{app}/venv/LIVE_ENV`
6. **Check uWSGI config**: `cat /home/hop3/uwsgi-enabled/{app}_web.1.ini`
7. **For Laravel**: Look for "Environment modified. Restarting server..." in logs
8. **For database issues**: Check addon is provisioned and env vars are correct
