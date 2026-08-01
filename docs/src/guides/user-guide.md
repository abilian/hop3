# Hop3 Guide

This guide provides a comprehensive overview of Hop3: the vision, deployment methods, and essential commands. For step-by-step tutorials, see [Quickstart](../get-started/quickstart.md). For exhaustive command documentation, see [CLI Reference](../reference/cli.md).

## Vision and Philosophy

Hop3 is an open-source Platform as a Service (PaaS) designed for **simplicity, security, and digital sovereignty**. It enables deployment and management of web applications on a single server.

### Core Principles

- **Self-hosted**: You own your infrastructure and data
- **Simple**: Heroku-like developer experience without the complexity
- **Flexible**: Native builds, Docker containers, or hermetic Nix builds
- **Standard**: Uses familiar conventions (Procfile, environment variables, 12-factor methodology)
- **Lightweight**: No Kubernetes or container orchestration required (though Docker is supported)

### When to Use Hop3

Hop3 is ideal for:

- Small to medium web applications
- Teams wanting full control over their infrastructure
- Projects requiring data sovereignty (GDPR compliance, etc.)
- Developers familiar with Heroku who want a self-hosted alternative
- Single-server deployments (VPS, dedicated server, or local VM)

## Deployment Methods

Hop3 supports four deployment strategies. Choose based on your application's needs.

### Method 1: Native Build (Recommended)

Hop3 detects your application type and builds it directly on the server using its language toolchains. This is the simplest approach and works well for most applications.

**Supported runtimes**: Python, Node.js, Ruby, Go, Rust, Java, PHP, Clojure, Elixir, .NET, static sites

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

### Method 3: Nix (hand-written expression)

For deployments that must be reproducible: the same inputs produce a
byte-identical artefact, verifiable by rebuilding.

**How it works**:

1. You provide a `hop3.nix` expression alongside your source
2. Nix builds it in a sandbox, offline, against a pinned dependency set
3. The built package declares how to run itself, and Hop3 runs it

**Advantages**:

- Reproducible: a rebuild is checkable against the first build
- No container runtime, and native process performance
- The full dependency graph is inspectable, from source to compiler

**Requirements**: a `hop3.nix` in the repository, and familiarity with the Nix
expression language.

### Method 4: Nix from a template (no Nix knowledge needed)

The same guarantees without writing Nix. Declare a template in `hop3.toml` and
Hop3 generates the expression for you.

```toml
[build]
builder = "nix"

[nix]
template = "python-venv"     # or php-app, go-source, node-pnpm-install, …
```

**How it works**: the template turns your project's existing lockfile
(`requirements.txt`, `composer.lock`, `go.sum`, `pnpm-lock.yaml`, `Gemfile.lock`)
into a vendored dependency set, then builds offline from it.

**Requirements**: a committed lockfile with pinned versions. Hop3 refuses to
build from unpinned dependencies, because the result could not be reproduced.

You can start from a template and later "eject" to a hand-written expression
with `hop3 nix eject --app <name>` if you need finer control.

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
- Custom names for other process types

Hop3 has no `release` process type. Run migrations with `[run].before-run` in
`hop3.toml`, which executes on every deploy before the app starts.

### hop3.toml

Optional configuration file for advanced settings. Provides more control than Procfile alone.
`hop3 scaffold` writes a starter one for the project in the current directory,
including a `#:schema` line so your editor can complete and validate the fields
as you type.

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

**Key sections:** `[metadata]`, `[build]`, `[run]`, `[env]`, `[[addons]]`, `[healthcheck]`, `[domains]`, `[[volumes]]`, `[[ports]]`, `[limits]`, `[backup]`

For complete documentation of all options, see the **[hop3.toml Reference](../reference/config.md)**.

### Using Both Together

You can use both Procfile and hop3.toml. Hop3 merges them with `hop3.toml` taking precedence for conflicting values.

## Essential Commands

### Initial Setup

```bash
# Initialize connection to your Hop3 server
hop3 init --ssh root@hop3.example.com

# Or login to an existing setup
hop3 auth login --ssh root@hop3.example.com

# Verify connection
hop3 auth whoami
hop3 system status

# Manage local CLI settings
hop3 settings
```

### Application Lifecycle

```bash
# List all applications
hop3 app list

# Create a new app from a git repository (then deploy it)
hop3 app create https://github.com/user/myapp.git --app myapp

# Deploy from local directory
cd myapp/
hop3 deploy --app myapp

# Start/stop/restart
hop3 app start --app myapp
hop3 app stop --app myapp
hop3 app restart --app myapp

# Check status and health
hop3 app status --app myapp
hop3 app ping --app myapp

# View logs (last 100 lines, or filter with --grep / -n)
hop3 app logs --app myapp
hop3 app logs --app myapp -n 50 --grep error

# Destroy an app (requires confirmation)
hop3 app destroy --app myapp
```

### Environment Configuration

```bash
# Show all config
hop3 env show --app myapp

# Set variables (restart required to take effect)
hop3 env set --app myapp LOG_LEVEL=info MAX_WORKERS=4
hop3 app restart --app myapp

# Get a specific variable
hop3 env get --app myapp DATABASE_URL

# Remove variables
hop3 env unset --app myapp OLD_KEY

# View live runtime config
hop3 env live --app myapp
```

### Process Management

```bash
# Show current process counts
hop3 ps --app myapp

# Scale processes
hop3 ps scale --app myapp web=3 worker=2

# Run one-off commands in app context
hop3 app run --app myapp python manage.py migrate
hop3 app run --app myapp npm run seed
hop3 app run --app myapp rails console
```

### Installing from the Catalog

The quickest way to get a working application is not to write a recipe at all.
Hop3 ships a signed catalog of ready-made applications.

```bash
# What is available
hop3 catalog list

# Install and deploy one (a hostname is assigned automatically)
hop3 catalog install bookstack

# Fetch the latest catalog from its publisher
hop3 catalog refresh
```

Each catalog application gets an administrator account generated at install
time. Retrieve it with:

```bash
hop3 app credentials --app bookstack
```

That password is the INITIAL one. If you change it inside the application, Hop3's
copy is stale — the output says so.

### Verifying an Application Works

A deployment that starts and returns HTTP 200 is not proof the application
works: a placeholder, an error page or a setup wizard all return 200. Catalog
applications ship a check that signs in through the application's own
authentication and confirms a wrong password is refused.

```bash
hop3 app check --app bookstack
```

This runs automatically at the end of every deploy, so a deploy that reports
success has also signed in. Run it yourself when you want to re-confirm.

### Upgrades and Rollback

```bash
# Snapshot, redeploy, run migrations, verify health — and restore the snapshot
# automatically if any of that fails
hop3 app upgrade --app myapp

# Roll back on demand (most recent backup by default)
hop3 app rollback --app myapp
hop3 app rollback --app myapp --to <backup-id>
```

### Domains and TLS

```bash
hop3 domain list --app myapp
hop3 domain add --app myapp app.example.com
hop3 domain remove --app myapp app.example.com

hop3 cert status --app myapp
hop3 cert renew --app myapp
```

See the **[Domains and Hostnames Guide](domains.md)** for DNS and certificate
setup.

### Backing Services (Addons)

```bash
# Create a PostgreSQL database
hop3 addon create postgres myapp-db

# Attach to app (injects DATABASE_URL)
hop3 addon attach myapp-db --app myapp
hop3 app restart --app myapp

# Create and attach Redis
hop3 addon create redis myapp-cache
hop3 addon attach myapp-cache --app myapp

# Get addon info
hop3 addon show myapp-db

# Detach from app
hop3 addon detach myapp-db --app myapp

# Destroy (requires confirmation)
hop3 addon destroy myapp-db
```

### Backups

```bash
hop3 backup create --app myapp   # Create backup
hop3 backup list --app myapp     # List backups for an app
hop3 backup restore <id>         # Restore from backup
hop3 app restart --app myapp     # Restart after restore
```

For complete backup documentation, see the **[Backup and Restore Guide](backup-restore.md)**.

### System Administration

```bash
# System status and info
hop3 system status
hop3 system info
hop3 system logs
hop3 system cleanup
```

### User Management (Admin only)

```bash
hop3 user list
hop3 user add alice alice@example.com --stdin   # read the password from stdin
hop3 user show alice
hop3 user set-password alice newpassword
hop3 user enable alice
hop3 user disable alice
hop3 user grant-admin alice
hop3 user revoke-admin alice
hop3 user remove alice
```

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
hop3 env set --app myapp $(cat .env | xargs)
```

**Step 3: Migrate addons**

| Heroku | Hop3 |
|--------|------|
| `heroku addon create heroku-postgresql` | `hop3 addon create postgres mydb` |
| `heroku addon create heroku-redis` | `hop3 addon create redis mycache` |

**Step 4: Deploy**

```bash
hop3 app create https://github.com/user/myapp.git --app myapp
hop3 deploy --app myapp
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
hop3 env set --app myapp \
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

[[ports]]
number = 8080
```

`[[ports]]` is for a fixed host port an app binds *directly* — SMTP, XMPP, RTMP.
Your HTTP port stays dynamic: Hop3 assigns `$PORT` and proxies to it, which is
what `internal_port` in `fly.toml` corresponds to, so there is usually nothing
to translate.

**Step 2: Migrate services and deploy**

```bash
hop3 addon create postgres mydb
hop3 app create <repo-url> --app myapp
hop3 addon attach mydb --app myapp
hop3 deploy --app myapp
```

### Migration Checklist

Before migrating, ensure:

- [ ] Procfile defines all processes (or hop3.toml `[run]` section)
- [ ] Environment variables documented/exported
- [ ] Database connection strings use standard `DATABASE_URL` format
- [ ] Application reads port from `$PORT` environment variable
- [ ] Static files paths configured if needed
- [ ] Health check endpoint available (recommended: `/health/`)
- [ ] Logs write to stdout/stderr (not files)

### Automatic Migration Helper

Convert an existing Procfile into a `hop3.toml`. The migrate command takes the
source format (currently only `procfile`) and the application directory as
positional arguments.

```bash
# Preview the generated hop3.toml without writing it
hop3 app migrate procfile /path/to/app --dry-run

# Write hop3.toml (backs up the original Procfile by default)
hop3 app migrate procfile /path/to/app --backup
```

## CLI Tips

### Output Formats

```bash
# JSON output for scripting
hop3 app list --json
hop3 app status --app myapp --json | jq '.data.state'

# Quiet mode (minimal output)
hop3 deploy --app myapp --quiet

# Verbose output for debugging
hop3 deploy --app myapp -v
hop3 deploy --app myapp --debug  # Maximum verbosity
```

### Automation

```bash
# Skip confirmation prompts
hop3 app destroy --app myapp -y
hop3 backup destroy <backup-id> -y

# Combine for CI/CD
hop3 deploy --app myapp --quiet -y
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

## Quick Reference

| Task | Command |
|------|---------|
| Browse ready-made apps | `hop3 catalog list` |
| Install a catalog app | `hop3 catalog install <id>` |
| Start a hop3.toml | `hop3 scaffold` |
| Create new app | `hop3 app create <repo-url> --app <name>` |
| Verify it works | `hop3 app check --app <name>` |
| Get admin credentials | `hop3 app credentials --app <name>` |
| Upgrade (auto-rollback) | `hop3 app upgrade --app <name>` |
| Add a domain | `hop3 domain add --app <name> <fqdn>` |
| Redeploy | `hop3 deploy --app <name>` |
| View logs | `hop3 app logs --app <name>` |
| Set config | `hop3 env set --app <name> KEY=val` |
| Scale processes | `hop3 ps scale --app <name> web=2` |
| Run command | `hop3 app run --app <name> <cmd>` |
| Add database | `hop3 addon create postgres <db-name>` |
| Attach database | `hop3 addon attach <db-name> --app <name>` |
| Create backup | `hop3 backup create --app <name>` |
| Restore backup | `hop3 backup restore <backup-id>` |
| System health | `hop3 system status` |
| Get help | `hop3 help <command>` |

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
