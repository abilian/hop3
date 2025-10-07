# hop3.toml Reference

This document provides a complete reference for the `hop3.toml` configuration format.

## Philosophy: Convention over Configuration

Hop3 follows the "Convention over Configuration" principle:

- **Procfile** is the **convention** (default, simple, Heroku-compatible)
- **hop3.toml** is the **configuration** (optional, advanced, full-featured)
- **Precedence**: `hop3.toml` > `Procfile` > defaults

You can use:
- **Procfile only** - Simple, works out of the box
- **hop3.toml only** - Full configuration control
- **Both together** - Use Procfile for basics, override with hop3.toml for advanced features

## Configuration Precedence

When both `Procfile` and `hop3.toml` are present:

1. Hop3 loads the Procfile first (convention)
2. Then loads hop3.toml (configuration)
3. hop3.toml values **override** Procfile values
4. Non-conflicting values are **merged**

Example:
```toml
# Procfile
web: gunicorn app:app
worker: celery worker

# hop3.toml
[run]
start = "uvicorn app:app"  # Overrides 'web' from Procfile

# Result:
# web: uvicorn app:app (from hop3.toml)
# worker: celery worker (from Procfile)
```

## File Location

Place `hop3.toml` in one of these locations (checked in order):
1. `src/hop3/hop3.toml`
2. `src/hop3.toml`
3. `hop3.toml` (project root)

## Sections

### [metadata] - Application Metadata

Optional section for application identification.

```toml
[metadata]
id = "my-app"               # Unique application identifier
version = "1.0.0"           # Application version
title = "My Application"    # Human-readable title
author = "Your Name <you@example.com>"  # Author information
```

**Fields:**
- `id` (string): Unique identifier for the application
- `version` (string): Semantic version number
- `title` (string): Display name for the application
- `author` (string): Author name and email

### [build] - Build Configuration

Controls how your application is built and prepared for deployment.

```toml
[build]
# Commands to run during build
build = ["npm run build", "make"]

# Commands to run before build
before-build = "npm ci"

# Test commands (smoke tests)
test = "npm test"

# System packages needed for build
packages = ["nodejs", "gcc", "make"]

# Python packages to install during build
pip-install = ["setuptools", "wheel"]
```

**Fields:**
- `build` (string | array): Main build commands
- `before-build` (string | array): Pre-build commands (maps to Procfile `prebuild`)
- `test` (string | array): Test commands to run after build
- `packages` (array): System packages required for building
- `pip-install` (array): Python packages to install during build

**Procfile Mapping:**
- `build.before-build` → Procfile `prebuild`

### [run] - Runtime Configuration

Defines how your application runs.

```toml
[run]
# Main application start command
start = "gunicorn app:app --workers 4"

# Commands to run before starting
before-run = ["python manage.py migrate", "python manage.py collectstatic --noinput"]

# System packages needed at runtime
packages = ["postgresql", "redis"]
```

**Fields:**
- `start` (string | array): Main application start command (maps to Procfile `web`)
- `before-run` (string | array): Pre-run commands (maps to Procfile `prerun`)
- `packages` (array): System packages required at runtime

**Procfile Mapping:**
- `run.start` → Procfile `web`
- `run.before-run` → Procfile `prerun`

### [env] - Environment Variables

Define environment variables for your application.

```toml
[env]
DEBUG = "false"
DATABASE_URL = "postgresql://localhost/mydb"
SECRET_KEY = "your-secret-key"
ALLOWED_HOSTS = "myapp.example.com"
```

**Note:** Sensitive values should be injected through actual environment variables, not hardcoded in hop3.toml.

### [port] - Port Configuration

Specify ports for different services.

```toml
[port]
web = 8000
api = 8080
metrics = 9090
```

### [healthcheck] - Health Check Configuration

Configure health check endpoints for monitoring.

```toml
[healthcheck]
path = "/health/"          # Health check endpoint path
timeout = 30              # Request timeout in seconds
interval = 60             # Check interval in seconds
```

**Fields:**
- `path` (string): HTTP path for health checks
- `timeout` (number): Timeout for health check requests
- `interval` (number): How often to run health checks

### [backup] - Backup Configuration

Configure automated backups for your application.

```toml
[backup]
enabled = true
schedule = "0 2 * * *"    # Cron expression (daily at 2 AM)
retention = 7             # Days to keep backups
```

**Fields:**
- `enabled` (boolean): Enable/disable automated backups
- `schedule` (string): Cron expression for backup schedule
- `retention` (number): Number of days to retain backups

### [[provider]] - Service Dependencies

Declare backing services your application needs (databases, caches, etc.).

```toml
[[provider]]
name = "postgres"
plan = "standard"
version = "15"

[[provider]]
name = "redis"
plan = "basic"
```

**Note:** Use `[[provider]]` (double brackets) for arrays in TOML.

**Fields:**
- `name` (string): Service type (postgres, redis, mysql, etc.)
- `plan` (string): Service plan/tier
- `version` (string): Service version

## Command Format

Commands can be specified as:

1. **Single string:**
   ```toml
   start = "python app.py"
   ```

2. **Array of strings** (executed with `&&`):
   ```toml
   before-run = ["python manage.py migrate", "python manage.py collectstatic"]
   # Equivalent to: python manage.py migrate && python manage.py collectstatic
   ```

## Examples

### Minimal Configuration

```toml
[metadata]
id = "my-app"

[run]
start = "python app.py"
```

### Python/Django Application

```toml
[metadata]
id = "django-blog"
version = "1.0.0"

[build]
before-build = "pip install -r requirements.txt"

[run]
start = "gunicorn blog.wsgi:application --workers 4"
before-run = "python manage.py migrate --noinput"

[env]
DJANGO_SETTINGS_MODULE = "blog.settings.production"

[[provider]]
name = "postgres"
plan = "standard"
```

### Node.js/Express Application

```toml
[metadata]
id = "express-api"
version = "1.0.0"

[build]
before-build = ["npm ci", "npm run build"]
test = "npm test"

[run]
start = "node dist/server.js"
packages = ["nodejs"]

[port]
web = 3000

[[provider]]
name = "postgres"
plan = "standard"
```

## Migration from Procfile

Use the migration command to convert an existing Procfile:

```bash
hop3 config:migrate-procfile /path/to/app --dry-run
```

This will generate a hop3.toml from your Procfile. Review and customize as needed.

## See Also

- [Procfile Reference](https://devcenter.heroku.com/articles/procfile)
- [Migration Guide](migration-guide.md)
- [Examples](examples/)
