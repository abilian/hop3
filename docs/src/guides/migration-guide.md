# Migration Guide

This guide helps you migrate applications to Hop3 from other platforms.

## Table of Contents

- [From Heroku](#from-heroku)
- [From Fly.io](#from-flyio)
- [From Procfile to hop3.toml](#from-procfile-to-hop3toml)

## From Heroku

Hop3 is designed to be Heroku-compatible at the Procfile level, making migration straightforward.

### Step 1: Copy Your Procfile

If you have a Heroku Procfile, it should work as-is in Hop3:

```bash
# Your existing Heroku Procfile
web: gunicorn myapp.wsgi:application
worker: celery -A myapp worker
```

Just copy it to your Hop3 application directory.

### Step 2: Migrate Environment Variables

Export your Heroku config:

```bash
heroku config -s --app myapp > .env
```

Set environment variables in Hop3:

```bash
# Using hop3-cli (one or more KEY=VALUE pairs)
hop3 env set --app myapp DATABASE_URL=postgresql://... SECRET_KEY=...

# Or add to hop3.toml
[env]
DATABASE_URL = "postgresql://..."
SECRET_KEY = "..."
```

### Step 3: Migrate Addons

Map Heroku addons to Hop3 services:

**Heroku Postgres:**
```bash
# Heroku
heroku addon create heroku-postgresql:standard-0

# Hop3
hop3 addon create postgres myapp-db
hop3 addon attach myapp-db --app myapp
```

**Heroku Redis:**
```bash
# Heroku
heroku addon create heroku-redis:premium-0

# Hop3
hop3 addon create redis myapp-cache
hop3 addon attach myapp-cache --app myapp
```

### Step 4: Deploy

```bash
hop3 deploy --app myapp
```

### Heroku → Hop3 Mapping

| Heroku | Hop3 | Notes |
|--------|------|-------|
| `heroku create` | `hop3 app launch <repo> --app myapp` | Create app from repo |
| `git push heroku main` | `hop3 deploy --app myapp` | Deploy code |
| `heroku config set` | `hop3 env set --app myapp` | Set env vars |
| `heroku addon create heroku-postgresql` | `hop3 addon create postgres` | Database |
| `heroku addon create heroku-redis` | `hop3 addon create redis` | Cache |
| `heroku ps` | `hop3 app status --app myapp` | Process status |
| `heroku logs -t` | `hop3 app logs --app myapp` | View logs |
| `heroku restart` | `hop3 app restart --app myapp` | Restart app |

### Common Gotchas

**1. Buildpacks**

Heroku uses buildpacks to detect the app type. Hop3 detects the language automatically; you can also pin it with the `toolchain` key:

```bash
# Heroku
heroku buildpacks:set heroku/python

# Hop3
# Automatic detection, or pin the language in hop3.toml:
[build]
toolchain = "python"
```

**2. Procfile Commands**

Some Heroku-specific commands may need adjustment:

```procfile
# Heroku release phase
release: python manage.py migrate

# Hop3 equivalent (use prerun)
prerun: python manage.py migrate
```

**3. Port Binding**

Heroku sets `$PORT` dynamically. Hop3 also provides `$PORT`:

```python
# Works on both Heroku and Hop3
port = int(os.environ.get("PORT", 8000))
```

## From Fly.io

Fly.io uses `fly.toml` for configuration. You can migrate to Hop3's `hop3.toml` format.

### Step 1: Convert fly.toml to hop3.toml

**Fly.io fly.toml:**
```toml
app = "myapp"

[build]
  builder = "paketobuildpacks/builder:base"

[env]
  PORT = "8080"

[[services]]
  internal_port = 8080
  protocol = "tcp"
```

**Hop3 hop3.toml:**
```toml
[metadata]
id = "myapp"

[run]
start = "python app.py"

[env]
PORT = "8080"

[port]
web = 8080
```

### Step 2: Migrate Services

**Fly.io Postgres:**
```bash
# Fly.io
fly postgres create --name myapp-db

# Hop3
hop3 addon create postgres myapp-db
hop3 addon attach myapp-db --app myapp
```

### Step 3: Deploy

```bash
hop3 deploy --app myapp
```

### Fly.io → Hop3 Mapping

| Fly.io | Hop3 | Notes |
|--------|------|-------|
| `fly launch` | `hop3 app launch <repo> --app myapp` | Create app from repo |
| `fly deploy` | `hop3 deploy --app myapp` | Deploy code |
| `fly secrets set` | `hop3 env set --app myapp` | Set secrets |
| `fly postgres create` | `hop3 addon create postgres` | Database |
| `fly status` | `hop3 app status --app myapp` | App status |
| `fly logs` | `hop3 app logs --app myapp` | View logs |
| `fly restart` | `hop3 app restart --app myapp` | Restart app |

## From Procfile to hop3.toml

If you want more control than Procfile provides, migrate to `hop3.toml`.

### Automatic Migration

Use the built-in migration command:

```bash
# Dry run - see what would be generated
hop3 config migrate procfile /path/to/app --dry-run

# Actually migrate
hop3 config migrate procfile /path/to/app
```

This will:
1. Parse your existing Procfile
2. Generate a hop3.toml file
3. Create a backup of your Procfile (Procfile.bak)

### Manual Migration

**Before (Procfile):**
```procfile
prebuild: npm ci && npm run build
prerun: npm run migrate
web: node dist/server.js
worker: node dist/worker.js
```

**After (hop3.toml):**
```toml
[metadata]
id = "my-app"
version = "1.0.0"

[build]
before-build = ["npm ci", "npm run build"]

[run]
start = "node dist/server.js"
before-run = "npm run migrate"

# Note: 'worker' process needs manual integration
# Consider using a process manager or separate deployment
```

### Why Migrate to hop3.toml?

**Advantages of hop3.toml:**
- More expressive (metadata, health checks, backups)
- Better for complex applications
- Supports environment-specific configuration
- Native TOML validation

**Keep using Procfile if:**
- You have a simple application
- You want maximum Heroku compatibility
- You prefer convention over configuration

### Using Both Together

You can use both Procfile and hop3.toml together:

```procfile
# Procfile - Basic worker definitions
web: gunicorn app:app
worker: celery worker
```

```toml
# hop3.toml - Advanced configuration
[metadata]
id = "my-app"

[build]
before-build = "pip install -r requirements.txt"

[healthcheck]
path = "/health/"
interval = 60

[[addons]]
type = "postgres"
```

Hop3 will merge these configurations with `hop3.toml` taking precedence.

## Environment-Specific Configuration

Hop3 uses a single `hop3.toml` configuration file. Environment-specific settings are handled through environment variables, which you can set differently per deployment.

### Production Configuration (hop3.toml)

```toml
# hop3.toml - used for all environments
[metadata]
id = "myapp"

[run]
start = "gunicorn app:app --workers 4"

[healthcheck]
path = "/health/"
```

### Environment Variables for Different Environments

```bash
# Production
hop3 env set --app myapp LOG_LEVEL=info

# Development/staging (local testing)
LOG_LEVEL=debug flask run --reload
```

For local development, run your app directly without Hop3. For deployed environments, use `hop3 env set` to configure environment-specific variables.

## Validation

After migration, validate your configuration:

```bash
# Check app configuration
hop3 env show --app myapp

# Deploy and verify
hop3 deploy --app myapp
hop3 app status --app myapp
hop3 app logs --app myapp
```

## Need Help?

- [hop3.toml Reference](../reference/config.md)
- [Configuration Examples](../developers/examples/)
- [FAQ](faq.md)
- [GitHub Issues](https://github.com/abilian/hop3/issues)
