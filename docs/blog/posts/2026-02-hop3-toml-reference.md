---
date: 2026-02-20
template: blog_post.html
description: Complete guide to every hop3.toml configuration option.
tags:
  - Reference
  - Configuration
---

# Designing hop3.toml: Configuration That Makes Sense

When we started building Hop3, we faced a familiar dilemma: how do you configure a deployment without drowning in YAML? Heroku and Piku use environment variables and Procfiles. Kubernetes uses... well, a lot of YAML. We wanted something in between—expressive enough to handle real applications, simple enough to understand at a glance.

We chose TOML. It's readable, it has proper data types, and it doesn't have YAML's indentation pitfalls. More importantly, it let us design a configuration that mirrors how developers actually think about their apps: "here's my app, here's how to build it, here's how to run it."

This post walks through every section of `hop3.toml`. Think of it as both a reference and a peek into our design decisions.

## The Basic Shape

A minimal `hop3.toml` looks like this:

```toml
[metadata]
id = "myapp"

[build]
toolchain = "python"

[run]
start = "gunicorn app:app"
before-run = ["python manage.py migrate"]

[env]
DEBUG = "false"

[static]
"/static" = "static/"

[healthcheck]
path = "/health"

[[addons]]
type = "postgres"
```

Each section handles one concern. No mixing build commands with runtime configuration. No environment variables scattered across files. Everything in one place.

## [metadata] — Who Is This App?

Every app needs an identity. The `metadata` section captures it:

```toml
[metadata]
id = "myapp"                    # Required: unique app identifier
version = "1.0.0"               # Optional: app version
title = "My Application"        # Optional: human-readable name
description = "A web app"       # Optional: description
author = "Your Name"            # Optional: author
license = "MIT"                 # Optional: license
```

The `id` is the only required field. It must be lowercase letters, numbers, and hyphens, start with a letter, and be 2-64 characters. We enforce this strictly because the ID becomes part of file paths, database names, and URLs.

## [build] — Getting Your App Ready

The build section controls how Hop3 transforms your source code into something runnable:

```toml
[build]
builder = "local"               # "local", "docker", or "auto"
toolchain = "python"            # Override auto-detection

# Commands
before-build = "npm install"    # Run before build (string or array)
build = "npm run build"         # Build commands
after-build = "npm run test"    # Run after build
test = "pytest"                 # Test/smoke test commands

# Dependencies
packages = ["libpq-dev"]        # System packages required for build
pip-install = ["wheel"]         # Python packages to pre-install

# Ignore patterns
ignore = ["node_modules", ".git"]
ignore-file = ".hop3ignore"     # File containing ignore patterns
```

Most of this is optional. Hop3 auto-detects your toolchain based on what files exist in your repo:

| Toolchain | Detected by |
|-----------|-------------|
| `python` | `requirements.txt`, `pyproject.toml` |
| `node` | `package.json` |
| `ruby` | `Gemfile` |
| `go` | `go.mod` |
| `rust` | `Cargo.toml` |
| `php` | `composer.json` |
| `java` | `pom.xml`, `build.gradle` |
| `clojure` | `project.clj` |
| `static` | `index.html` |

The `builder` option is interesting. By default (`auto`), Hop3 builds directly on the server using the native toolchain. But you can force Docker builds if you need isolation or specific system dependencies. We found that most apps don't need containerized builds—they're slower and more complex—but the option is there when you need it.

## [run] — Keeping Your App Alive

This is where you tell Hop3 how to actually run your application:

```toml
[run]
start = "gunicorn app:app -b 0.0.0.0:$PORT"
before-run = ["python manage.py migrate", "python manage.py collectstatic"]
packages = ["libpq5"]           # System packages for runtime
start-timeout = 30              # Seconds to wait for app to start
healthcheck = "/health"         # Health check path
healthcheck-timeout = 5         # Health check timeout in seconds

[run.workers]
worker = "celery -A app worker"
scheduler = "celery -A app beat"
```

The `before-run` commands are one of our most-used features. They run every time the app starts—perfect for database migrations, static file collection, or cache warming. If any command fails, the deployment stops. No partial deployments, no broken state.

### A Note on Workers

The `[run.workers]` section deserves special attention. Each key defines a separate process type:

```toml
[run.workers]
web = "gunicorn app:app"        # Override the default web process
worker = "celery -A app worker"
scheduler = "celery -A app beat"
cron = "python manage.py runcrons"
```

Workers are managed independently. You can scale them separately (`hop3 ps:scale worker=3`), restart them individually, and monitor them in isolation. This mirrors how Heroku's dynos work, and it's one of the patterns we explicitly borrowed.

## [env] — Configuration Without Code Changes

Environment variables live in their own section:

```toml
[env]
DEBUG = "false"
LOG_LEVEL = "info"
SECRET_KEY = "generate-a-real-secret"
ALLOWED_HOSTS = "myapp.example.com"
```

One gotcha: **values must be strings**. TOML distinguishes between `"8000"` (string) and `8000` (integer), but environment variables are always strings. We enforce this to avoid surprises:

```toml
[env]
PORT = "8000"           # Correct
# PORT = 8000           # Wrong - this is a TOML integer, not a string
```

Some variables are special. `HOST_NAME` configures your domain for the reverse proxy and SSL. `PORT` is auto-injected—you shouldn't set it yourself. `DATABASE_URL` gets injected when you attach database addons.

## [static] — Let Nginx Handle the Heavy Lifting

Static files can bypass your application entirely:

```toml
[static]
"/static" = "static/"
"/media" = "media/"
"/favicon.ico" = "static/favicon.ico"
```

The left side is the URL path, the right side is the filesystem path relative to your app's source. Nginx serves these directly, which is dramatically faster than having Python or Node serve static files.

We debated whether to auto-detect static directories. We decided against it—explicit configuration is clearer, and it prevents accidental exposure of directories you didn't intend to serve.

## [healthcheck] — Knowing When Things Break

Health checks let Hop3 monitor your application:

```toml
[healthcheck]
path = "/health"        # HTTP path to check
interval = 30           # Check interval in seconds
timeout = 5             # Request timeout in seconds
retries = 3             # Failures before marking unhealthy
```

Your health endpoint should be lightweight. A simple "is the database reachable?" check is usually enough:

```python
@app.route("/health")
def health():
    try:
        db.session.execute("SELECT 1")
        return "OK", 200
    except Exception:
        return "Database unavailable", 503
```

When health checks fail repeatedly, Hop3 can restart your app automatically. This isn't magic—it's just automation of what you'd do manually when things go wrong.

## [[addons]] — Databases and Beyond

The double-bracket syntax declares database addons:

```toml
[[addons]]
type = "postgres"
name = "main-db"        # Optional: instance name

[[addons]]
type = "redis"
name = "cache"
```

When you deploy, Hop3 provisions these services and injects connection strings:

| Type | Injected Variables |
|------|-------------------|
| `postgres` | `DATABASE_URL`, `POSTGRES_*` |
| `mysql` | `DATABASE_URL`, `MYSQL_*` |
| `redis` | `REDIS_URL` |

We originally used `[[provider]]` for this, but "addon" is clearer. The old syntax still works—we don't break existing configs.

## The Less Common Sections

A few more sections handle specialized needs:

### [backup]

```toml
[backup]
paths = ["uploads/", "data/"]   # Directories to include
exclude = ["*.tmp", "cache/*"]  # Patterns to exclude
```

Backups include your specified paths, database dumps, and environment configuration. Everything you need to restore from scratch.

### [docker]

```toml
[docker]
port = 8000             # Container port to expose

[docker.build-args]
NODE_ENV = "production"
```

Only relevant if you're using `builder = "docker"`. Most apps don't need this.

### [port]

```toml
[port.web]
container = 8000        # Internal port
public = true           # Expose publicly
https = true            # Enable HTTPS

[port.metrics]
container = 9090
public = false          # Internal only
```

For apps that expose multiple ports. The default configuration handles most cases automatically.

## Putting It All Together

Here's a complete `hop3.toml` for a Django application with Celery workers:

```toml
[metadata]
id = "django-app"
version = "2.0.0"
title = "My Django App"

[build]
toolchain = "python"
before-build = "pip install -r requirements.txt"
packages = ["libpq-dev"]

[run]
start = "gunicorn myapp.wsgi:application -b 0.0.0.0:$PORT"
before-run = [
    "python manage.py migrate --noinput",
    "python manage.py collectstatic --noinput",
]
packages = ["libpq5"]

[run.workers]
worker = "celery -A myapp worker -l info"
beat = "celery -A myapp beat -l info"

[env]
DJANGO_SETTINGS_MODULE = "myapp.settings.production"
DEBUG = "false"
HOST_NAME = "myapp.example.com"

[static]
"/static" = "staticfiles/"
"/media" = "media/"

[healthcheck]
path = "/health/"
timeout = 5
retries = 3

[[addons]]
type = "postgres"

[[addons]]
type = "redis"

[backup]
paths = ["media/"]
```

It's longer than a `Procfile`, but everything is in one place. No hunting through environment variables or multiple files to understand how the app runs.

## When You Make a Mistake

We validate `hop3.toml` strictly. Typos get caught early:

```
ERROR: Invalid hop3.toml configuration:
  - Unknown field 'post-deploy'
    Did you mean 'before-run'?

Hint: Check the hop3.toml reference for valid fields:
  https://hop3.cloud/reference/config/
```

This is intentional. Silent failures—where Hop3 ignores a typo and your migration never runs—are worse than loud errors. We'd rather reject your deploy and tell you exactly what's wrong.

## IDE Support

We generate a JSON Schema from our Pydantic models. VS Code with the "Even Better TOML" extension can use it for autocompletion and validation as you type. Check our documentation for the latest schema location.

---

Configuration is boring until it isn't. A well-designed config file saves hours of debugging. We've tried to make `hop3.toml` something you can read six months later and immediately understand.

*See also: [Configuration Validation](2026-02-configuration-validation.md) explains how we catch typos and provide helpful error messages. For a practical walkthrough, check out [Your First Hop3 Deployment](2026-01-deploying-first-app.md).*
