# Hop3 Guide

This guide provides a comprehensive overview of Hop3: the vision, deployment methods, and essential commands. For step-by-step tutorials, see [Quickstart](../get-started/quickstart.md). For exhaustive command documentation, see [CLI Reference](../reference/cli.md).

---

## Vision and Philosophy

Hop3 is an open-source Platform as a Service (PaaS) designed for **simplicity, security, and digital sovereignty**. It enables deployment and management of web applications on a single server.

### Core Principles

- **Self-hosted**: You own your infrastructure and data
- **Simple**: Heroku-like developer experience without the complexity
- **Flexible**: Supports both native builds and Docker containers
- **Standard**: Uses familiar conventions (Procfile, environment variables, 12-factor methodology)
- **Lightweight**: No Kubernetes or container orchestration required (though Docker is supported)

### When to Use Hop3

Hop3 is ideal for:

- Small to medium web applications
- Teams wanting full control over their infrastructure
- Projects requiring data sovereignty (GDPR compliance, etc.)
- Developers familiar with Heroku who want a self-hosted alternative
- Single-server deployments (VPS, dedicated server, or local VM)

---

## Deployment Methods

Hop3 supports two deployment strategies. Choose based on your application's needs.

### Method 1: Native Build (Recommended)

Hop3 detects your application type and builds it directly on the server using buildpacks. This is the simplest approach and works well for most applications.

**Supported runtimes**: Python, Node.js, Ruby, Go, Rust, Java, PHP, static sites

**How it works**:

1. You provide source code with a `Procfile` (and optionally `hop3.toml`)
2. Hop3 detects the language/framework from files present
3. Dependencies are installed in an isolated environment
4. Application processes are started and managed

**Advantages**:

- Simpler configuration
- Smaller resource footprint
- Faster deployments for supported languages
- Direct access to application files for debugging

**Requirements**:

- A `Procfile` defining your processes
- Language-specific dependency file (`requirements.txt`, `package.json`, `Gemfile`, etc.)
- Optionally, a `hop3.toml` for advanced configuration

### Method 2: Docker Build

For applications that need custom environments, complex dependencies, or specific system packages.

**How it works**:

1. You provide a `Dockerfile` in your repository
2. Hop3 builds the Docker image on the server
3. Container is run with proper networking and environment

**Advantages**:

- Full control over the runtime environment
- Any language or stack supported
- Reproducible builds across environments
- Complex dependencies handled easily

**Requirements**:

- A `Dockerfile` in your repository root
- Application must listen on the port specified by `$PORT` environment variable

**When to choose Docker**:

- Application requires specific system libraries
- Using unsupported languages or custom runtimes
- Need exact reproducibility across environments
- Complex multi-service build process

---

## Configuration Files

### Procfile

The Procfile defines the processes your application runs. This is the minimum required configuration.

```procfile
# Basic web application
web: gunicorn app:application -b 0.0.0.0:$PORT

# With background worker
web: gunicorn app:application -b 0.0.0.0:$PORT
worker: celery -A tasks worker --loglevel=info

# Node.js application
web: node server.js

# Static site (uses built-in server)
web: python -m http.server $PORT
```

**Process types**:

- `web`: The main HTTP-serving process (required for web apps)
- `worker`: Background job processors
- `release`: Run once after build, before deploy (migrations, etc.)
- Custom names for other process types

### hop3.toml

Optional configuration file for advanced settings. Provides more control than Procfile alone.

```toml
[metadata]
id = "myapp"
version = "1.0.0"

[build]
builder = "local"

[run]
start = "gunicorn app:app --workers 4 -b 0.0.0.0:$PORT"
before-run = "python manage.py migrate"

[env]
LOG_LEVEL = "info"

[healthcheck]
path = "/health/"
```

**Key sections:** `[metadata]`, `[build]`, `[run]`, `[env]`, `[port]`, `[healthcheck]`, `[backup]`, `[[provider]]`

For complete documentation of all options, see the **[hop3.toml Reference](../reference/config.md)**.

### Using Both Together

You can use both Procfile and hop3.toml. Hop3 merges them with `hop3.toml` taking precedence for conflicting values.

---

## Essential Commands

### Initial Setup

```bash
# Initialize connection to your Hop3 server
hop3 init --ssh root@hop3.example.com

# Or login to an existing setup
hop3 login --ssh root@hop3.example.com

# Verify connection
hop3 auth:whoami
hop3 system:status

# Manage local CLI settings
hop3 settings
```

### Application Lifecycle

```bash
# List all applications
hop3 apps

# Create and deploy from git repository
hop3 app:launch https://github.com/user/myapp.git myapp

# Deploy from local directory
cd myapp/
hop3 deploy myapp

# Start/stop/restart
hop3 app:start myapp
hop3 app:stop myapp
hop3 app:restart myapp

# Check status and health
hop3 app:status myapp
hop3 app:ping myapp

# View logs (real-time with -f)
hop3 app:logs myapp
hop3 app:logs myapp -f

# Destroy an app (requires confirmation)
hop3 app:destroy myapp
```

### Environment Configuration

```bash
# Show all config
hop3 config:show myapp

# Set variables (restart required to take effect)
hop3 config:set myapp LOG_LEVEL=info MAX_WORKERS=4
hop3 app:restart myapp

# Get a specific variable
hop3 config:get myapp DATABASE_URL

# Remove variables
hop3 config:unset myapp OLD_KEY

# View live runtime config
hop3 config:live myapp
```

### Process Management

```bash
# Show current process counts
hop3 ps myapp

# Scale processes
hop3 ps:scale myapp web=3 worker=2

# Run one-off commands in app context
hop3 run myapp python manage.py migrate
hop3 run myapp npm run seed
hop3 run myapp rails console
```

### Backing Services (Addons)

```bash
# Create a PostgreSQL database
hop3 addons:create postgres myapp-db

# Attach to app (injects DATABASE_URL)
hop3 addons:attach myapp-db --app myapp
hop3 app:restart myapp

# Create and attach Redis
hop3 addons:create redis myapp-cache
hop3 addons:attach myapp-cache --app myapp

# Get addon info
hop3 addons:info myapp-db

# Detach from app
hop3 addons:detach myapp-db --app myapp

# Destroy (requires confirmation)
hop3 addons:destroy myapp-db
```

### Backups

```bash
hop3 backup:create myapp     # Create backup
hop3 backup:list myapp       # List backups
hop3 backup:restore <id>     # Restore from backup
hop3 app:restart myapp       # Restart after restore
```

For complete backup documentation, see the **[Backup and Restore Guide](backup-restore.md)**.

### System Administration

```bash
# System status and info
hop3 system:status
hop3 system:info
hop3 system:uptime
hop3 system:ps
hop3 system:logs
```

### User Management (Admin only)

```bash
hop3 admin:user:list
hop3 admin:user:add alice alice@example.com password123
hop3 admin:user:info alice
hop3 admin:user:set-password alice newpassword
hop3 admin:user:enable alice
hop3 admin:user:disable alice
hop3 admin:user:grant-admin alice
hop3 admin:user:revoke-admin alice
hop3 admin:user:remove alice
```

---

## Porting Applications to Hop3

### From Heroku

Hop3 is designed for Heroku compatibility. Most Heroku apps work with minimal changes.

**Step 1: Your Procfile works as-is**

```procfile
web: gunicorn myapp.wsgi:application
worker: celery -A myapp worker
```

**Step 2: Export and migrate config**

```bash
# Export from Heroku
heroku config -s --app myapp > .env

# Set in Hop3
hop3 config:set myapp $(cat .env | xargs)
```

**Step 3: Migrate addons**

| Heroku | Hop3 |
|--------|------|
| `heroku addons:create heroku-postgresql` | `hop3 addons:create postgres mydb` |
| `heroku addons:create heroku-redis` | `hop3 addons:create redis mycache` |

**Step 4: Deploy**

```bash
hop3 app:launch https://github.com/user/myapp.git myapp
hop3 deploy myapp
```

### From Docker Compose

**Step 1: Create a Procfile from your services**

```yaml
# docker-compose.yml
services:
  web:
    command: gunicorn app:app
  worker:
    command: celery worker
```

Becomes:

```procfile
web: gunicorn app:app -b 0.0.0.0:$PORT
worker: celery worker
```

**Step 2: Extract environment variables**

Move environment variables from `docker-compose.yml` to Hop3:

```bash
hop3 config:set myapp \
  DATABASE_URL=postgresql://... \
  REDIS_URL=redis://...
```

**Step 3: Choose deployment method**

- **Option A (Native)**: Remove Dockerfile, let Hop3 build natively
- **Option B (Docker)**: Keep Dockerfile, Hop3 builds and runs it

### From Fly.io

**Step 1: Convert fly.toml to hop3.toml**

```toml
# fly.toml
app = "myapp"
[env]
  PORT = "8080"
[[services]]
  internal_port = 8080
```

Becomes:

```toml
# hop3.toml
[metadata]
id = "myapp"

[env]
PORT = "8080"

[port.web]
container = 8080
public = true
```

**Step 2: Migrate services and deploy**

```bash
hop3 addons:create postgres mydb
hop3 app:launch <repo-url> myapp
hop3 addons:attach mydb --app myapp
hop3 deploy myapp
```

### Migration Checklist

Before migrating, ensure:

- [ ] Procfile defines all processes (or hop3.toml [run] section)
- [ ] Environment variables documented/exported
- [ ] Database connection strings use standard `DATABASE_URL` format
- [ ] Application reads port from `$PORT` environment variable
- [ ] Static files paths configured if needed
- [ ] Health check endpoint available (recommended: `/health/`)
- [ ] Logs write to stdout/stderr (not files)

### Automatic Migration Helper

```bash
# Preview migration from Procfile
hop3 config:migrate --format procfile --dry-run

# Apply migration
hop3 config:migrate --format procfile --backup

# From Heroku format
hop3 config:migrate --format heroku --dry-run
```

---

## CLI Tips

### Output Formats

```bash
# JSON output for scripting
hop3 apps --json
hop3 app:status myapp --json | jq '.data.state'

# Quiet mode (minimal output)
hop3 deploy myapp --quiet

# Verbose output for debugging
hop3 deploy myapp -v
hop3 deploy myapp --debug  # Maximum verbosity
```

### Automation

```bash
# Skip confirmation prompts
hop3 app:destroy myapp -y
hop3 backup:delete backup-id -y

# Combine for CI/CD
hop3 deploy myapp --quiet -y
```

### Environment Variables

```bash
# Override server URL
export HOP3_API_URL="https://hop3.example.com"

# Override token
export HOP3_API_TOKEN="your-token-here"

# Enable debug logging
export HOP3_DEBUG=1
```

---

## Quick Reference

| Task | Command |
|------|---------|
| Deploy new app | `hop3 app:launch <repo-url> <name>` |
| Redeploy | `hop3 deploy <name>` |
| View logs | `hop3 app:logs <name>` |
| Set config | `hop3 config:set <name> KEY=val` |
| Scale processes | `hop3 ps:scale <name> web=2` |
| Run command | `hop3 run <name> <cmd>` |
| Add database | `hop3 addons:create postgres <db-name>` |
| Attach database | `hop3 addons:attach <db-name> --app <name>` |
| Create backup | `hop3 backup:create <name>` |
| Restore backup | `hop3 backup:restore <backup-id>` |
| System health | `hop3 system:status` |
| Get help | `hop3 help <command>` |

---

## Next Steps

- **[Quickstart](../get-started/quickstart.md)** - Step-by-step first deployment tutorial
- **[Domains and Hostnames](domains.md)** - Configure custom domains and SSL certificates
- **[Backup and Restore](backup-restore.md)** - Comprehensive backup documentation
- **[CLI Reference](../reference/cli.md)** - Complete command documentation
- **[hop3.toml Reference](../reference/config.md)** - Full configuration file reference
- **[Troubleshooting](troubleshooting.md)** - Diagnose and fix common issues
- **[FAQ](faq.md)** - Frequently asked questions

For help at any time:

```bash
hop3 help
hop3 help <command>
```
