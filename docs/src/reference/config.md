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
# Builder to use: "auto", "local", or "docker"
builder = "local"

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
- `builder` (string): Which builder to use for deployment:
  - `"auto"` (default): Auto-detect based on project files (Dockerfile → docker, otherwise local)
  - `"local"`: Use native language toolchains (Python, Node, Ruby, etc.) directly on host
  - `"docker"`: Build and run using Docker (requires Dockerfile)
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

# Startup timeout in seconds (default: 60 = 1 minute)
start-timeout = 120
```

**Fields:**
- `start` (string | array): Main application start command (maps to Procfile `web`)
- `before-run` (string | array): Pre-run commands (maps to Procfile `prerun`)
- `packages` (array): System packages required at runtime
- `start-timeout` (number): Maximum time in seconds to wait for the app to start (default: 60)

**Procfile Mapping:**
- `run.start` → Procfile `web`
- `run.before-run` → Procfile `prerun`

**Startup Timeout:**

The `start-timeout` option controls how long Hop3 waits for your application to start before marking the deployment as failed. This is useful for applications with slow startup times (e.g., Java apps, apps with large dependency trees).

```toml
[run]
start-timeout = 120  # Wait up to 2 minutes for app to start
```

The server-wide default is 60 seconds (1 minute), configurable via the `APP_START_TIMEOUT` environment variable on the server. During the wait, Hop3 streams log output so you can see what's happening.

### [env] - Environment Variables

Define environment variables for your application.

```toml
[env]
DATABASE_URL = "postgresql://localhost/mydb"
SECRET_KEY = "your-secret-key"
ALLOWED_HOSTS = "myapp.example.com"
LOG_LEVEL = "info"
```

**Notes:**

- Sensitive values should be injected through `hop3 config:set`, not hardcoded in hop3.toml.
- The `DEBUG` environment variable defaults to `false`. Only set `DEBUG = "true"` in development environments for troubleshooting—never in production.

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

## `[nix]` — Template-Based Nix Builds

When `builder = "nix"` is set in `[build]`, Hop3 can generate a Nix expression automatically from a `[nix]` section instead of requiring a hand-crafted `hop3.nix` file. This removes the Nix learning curve for most deployments.

### How It Works

1. If a `hop3.nix` file exists in the source directory, it is used directly (hand-crafted mode).
2. If no `hop3.nix` exists but `[nix].template` is set, Hop3 generates one at build time from the template.
3. Run `hop3 nix:eject <app>` to materialize the generated file for manual customization.

### Template Types

Eight templates are available. Prefer the higher tiers when possible
— see [Nix reference](nix.md#reproducibility-tiers) for the
reproducibility implications.

| Template | Use case | Tier |
|----------|----------|------|
| `nixpkgs-wrapper` | Apps already packaged in nixpkgs (best — multi-arch, source-built) | 1 |
| `python-venv` | Python apps installed via pip into a virtualenv | 2 |
| `php-app` | PHP apps served with `php -S` or `artisan serve` | 2 |
| `java-war` | Java WAR files served with a JDK from nixpkgs | 1 |
| `ruby-bundler` | Ruby apps using `bundlerEnv` from `gemset.nix` | 2 |
| `prebuilt-binary` | Pre-compiled single binary from upstream releases | 3 |
| `prebuilt-archive` | Pre-compiled archive with multiple files | 3 |
| `node-prebuilt` | Node.js apps with pre-built assets | 3 |

**Tier 1 = source-built and reproducible** (use when available).
**Tier 2 = source-built but not fully hermetic** (depends on PyPI,
Packagist, etc. at build time).
**Tier 3 = pre-built binary download** (x86_64-linux only, not
reproducible from source — use only when nothing in nixpkgs fits).

### Common Fields

```toml
[nix]
template = "prebuilt-binary"   # Required: template type
url = "https://..."            # Source URL (supports ${version} interpolation)
sha256 = "abc123..."           # SHA-256 hash for source verification
executable = false             # true for single-binary downloads
archive = "tar-gz"             # "tar-gz", "tar-bz2", "tar-xz", "zip", or omit
binary-name = "myapp"          # Name of the binary (prebuilt-binary)
exec-target = "myapp"          # What to exec in the wrapper
exec-args = ["serve"]          # Arguments appended to exec
extra-paths = ["${php}/bin"]   # PATH entries for runtime.json
```

### Wrapper Script Fields

These configure the shell wrapper that runs at application startup:

```toml
[nix.local-vars]               # Shell variables (not exported)
PORT = "${PORT:-8080}"

[nix.env-exports]              # Exported environment variables
NODE_ENV = "production"

[nix.runtime-env]              # Default env vars in runtime.json
APP_ENV = "production"

[[nix.conditional-env]]        # Set only if not already defined
name = "DATABASE_URL"
condition-var = "DATABASE_URL"
value = "postgres://${PGUSER}@${PGHOST}:${PGPORT}/${PGDATABASE}"
```

### Config File Generation

Generate config files at startup with runtime variable substitution:

```toml
[[nix.config-files]]
path = "custom/conf/app.ini"
format = "ini"                  # "ini" or "raw"
create-if-missing = false       # Only create if file doesn't exist

[nix.config-files.sections.server]
HTTP_PORT = "${PORT}"

[nix.config-files.sections.database]
HOST = "${PGHOST}:${PGPORT}"
```

For JSON, YAML, or complex configs, use `format = "raw"`:

```toml
[[nix.config-files]]
path = "config.json"
format = "raw"
raw-content = """
{
  "port": ${PORT},
  "db": "postgres://${PGUSER}@${PGHOST}/${PGDATABASE}"
}
"""
```

### PHP-Specific Fields

```toml
[nix]
template = "php-app"
php-version = "php82"
php-extensions = ["mysqli", "gd", "mbstring", "xml"]
needs-composer = true
composer-extra-flags = ["--ignore-platform-reqs"]
serve-mode = "builtin"         # "builtin" (php -S) or "artisan"
web-root = "htdocs"            # Subdirectory for document root
post-install-dirs = ["storage/logs", "bootstrap/cache"]
```

### Complete Example (Gitea via nixpkgs-wrapper — Tier 1)

This is the recommended pattern: wrap a nixpkgs source build with a
startup script that generates the app.ini config from environment
variables.

```toml
[metadata]
id = "gitea"
description = "Self-hosted Git service"

[build]
builder = "nix"

[nix]
template = "nixpkgs-wrapper"
nixpkgs-package = "gitea"
exec-target = "gitea"
exec-args = ["web"]
extra-paths = ["${gitea}/bin"]
pre-exec = ["mkdir -p custom/conf data"]

[nix.local-vars]
PORT = "${PORT:-8080}"
DB_HOST = "${PGHOST:-localhost}"
DB_PORT = "${PGPORT:-5432}"
DB_NAME = "${PGDATABASE:-gitea}"
DB_USER = "${PGUSER:-gitea}"
DB_PASS = "${PGPASSWORD:-}"

[nix.env-exports]
GITEA_WORK_DIR = "$PWD"

[[nix.config-files]]
path = "custom/conf/app.ini"
format = "ini"

[nix.config-files.sections.server]
HTTP_PORT = "${PORT}"
ROOT_URL = "http://localhost:${PORT}/"

[nix.config-files.sections.database]
DB_TYPE = "postgres"
HOST = "${DB_HOST}:${DB_PORT}"
NAME = "${DB_NAME}"
USER = "${DB_USER}"
PASSWD = "${DB_PASS}"

[nix.config-files.sections.security]
INSTALL_LOCK = "true"
SECRET_KEY = "$(head -c 32 /dev/urandom | base64)"

[[addons]]
type = "postgres"
```

## Migration from Procfile

Use the migration command to convert an existing Procfile:

```bash
hop3 config:migrate procfile /path/to/app --dry-run
```

This will generate a hop3.toml from your Procfile. Review and customize as needed.

## See Also

- [Procfile Reference](https://devcenter.heroku.com/articles/procfile)
- [Migration Guide](migration-guide.md)
- [Examples](examples/)
