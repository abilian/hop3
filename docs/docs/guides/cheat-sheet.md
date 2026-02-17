# Hop3 Cheat Sheet

A quick reference for Hop3 users.

## Mental Model

Hop3 is a **single-server PaaS** (Platform as a Service). Think of it as:

```
Your Code  →  hop3 deploy  →  Running App on Your Server
```

**Key concepts:**

1. **Apps** are deployable units. Each app has a name, source code, config, and runtime.
2. **Configuration** comes from three layers (lowest to highest priority):
   - Defaults (provided by Hop3)
   - `Procfile` (convention, Heroku-compatible)
   - `hop3.toml` (full configuration)
3. **Addons** are backing services (databases, caches) that attach to apps.
4. **Environment variables** configure runtime behavior.
5. **The CLI** talks to the server via JSON-RPC; most commands run remotely.

---

## Quick Reference: Commands

### Setup & Authentication

```bash
# First time: initialize connection and create admin
hop3 init --ssh root@hop3.example.com

# Log in to existing server
hop3 login --ssh root@hop3.example.com

# Check who you're logged in as
hop3 auth:whoami

# Get version
hop3 version
```

### Context Management (Multiple Servers)

```bash
# Add server contexts
hop3 context add staging --server ssh://root@staging.example.com
hop3 context add production --server ssh://root@prod.example.com --protected

# List contexts (* = current)
hop3 context list

# Show current context and source
hop3 context current

# Switch context (safe - prints export command)
hop3 context use production
# Output: export HOP3_CONTEXT=production

# Switch context for this directory
hop3 context use staging --local

# Switch context globally (affects all terminals - use with caution!)
hop3 context use production --global

# Use context for single command
hop3 --context production apps

# Remove context
hop3 context remove old-staging
```

**Context priority (highest to lowest):**
1. `--context` flag
2. `HOP3_CONTEXT` environment variable
3. `.hop3-context` file in current directory
4. Global config

### Application Lifecycle

```bash
# Create app from git repository
hop3 app:launch <git-url> <app-name>

# Deploy (from project directory)
hop3 deploy <app-name>

# Deploy from a specific directory
hop3 deploy <app-name> /path/to/app

# Check status
hop3 app:status <app>

# View logs (streaming)
hop3 app:logs <app>

# Build logs
hop3 app:build-logs <app>

# Start / Stop / Restart
hop3 app:start <app>
hop3 app:stop <app>
hop3 app:restart <app>

# List all apps
hop3 apps

# Destroy app (requires confirmation)
hop3 app:destroy <app>
```

### Configuration / Environment

```bash
# View all env vars
hop3 config:show <app>

# Get single var
hop3 config:get <app> VAR_NAME

# Set vars (one or multiple)
hop3 config:set <app> VAR1=value1 VAR2=value2

# Remove var
hop3 config:unset <app> VAR_NAME

# Live runtime config
hop3 config:live <app>

# Migrate Procfile to hop3.toml
hop3 config:migrate procfile /path/to/app --dry-run
```

### Addons (Backing Services)

```bash
# List available addon types
hop3 addons:list

# Create addon
hop3 addons:create postgres my-db

# Attach to app (injects DATABASE_URL, etc.)
hop3 addons:attach my-db --app <app>

# Detach from app
hop3 addons:detach my-db --app <app>

# Check addon info
hop3 addons:info my-db

# Destroy addon
hop3 addons:destroy my-db
```

### Backups

```bash
# Create backup
hop3 backup:create <app>

# List backups
hop3 backup:list <app>

# Restore
hop3 backup:restore <backup-id>
hop3 app:restart <app>

# Delete backup
hop3 backup:delete <backup-id>
```

### Process Scaling

```bash
# View processes
hop3 ps <app>

# Scale (web=2, worker=1)
hop3 ps:scale <app> web=2 worker=1
```

### System & Admin

```bash
# System info
hop3 system:info
hop3 system:status
hop3 system:uptime

# List all server processes
hop3 system:ps

# Server logs
hop3 system:logs

# User management (admin only)
hop3 admin:user:list
hop3 admin:user:add <username>
hop3 admin:user:disable <username>
hop3 admin:user:enable <username>
```

### Help

```bash
# General help
hop3 help

# All commands
hop3 help --all

# Help for specific command
hop3 <command> --help
```

---

## CLI Flags

| Flag | Effect |
|------|--------|
| `--json` | JSON output (for scripting) |
| `--quiet` / `-q` | Suppress output |
| `--verbose` / `-v` | More detail |
| `-y` / `--yes` | Skip confirmations |
| `--context <name>` | Use specific server context |
| `--help` / `-h` | Show help |

**Scripting example:**

```bash
# Get app state in JSON
hop3 app:status myapp --json | jq '.data.state'

# Destroy without prompt (use with caution)
hop3 app:destroy myapp -y
```

---

## Configuration Files

### Procfile (Simple / Heroku-compatible)

Location: `Procfile` in project root.

```procfile
web: gunicorn app:app --workers 4
worker: celery -A myapp worker
prebuild: pip install -r requirements.txt
prerun: python manage.py migrate
```

| Key | Purpose |
|-----|---------|
| `web` | Main process (receives HTTP traffic) |
| `worker` | Background worker |
| `prebuild` | Runs before build |
| `prerun` | Runs before start |

### hop3.toml (Full Configuration)

Location: `hop3.toml` in project root (or `src/hop3.toml`).

```toml
[metadata]
id = "myapp"
version = "1.0.0"
title = "My Application"

[build]
before-build = "pip install -r requirements.txt"
build = "npm run build"
test = "pytest"
packages = ["nodejs", "gcc"]

[run]
start = "gunicorn app:app --workers 4"
before-run = "python manage.py migrate"
packages = ["postgresql-client"]

[env]
DEBUG = "false"
LOG_LEVEL = "info"

[port]
web = 8000

[healthcheck]
path = "/health/"
timeout = 30
interval = 60

[backup]
enabled = true
schedule = "0 2 * * *"
retention = 7

[[provider]]
name = "postgres"
plan = "standard"
```

### Key Sections

| Section | Purpose |
|---------|---------|
| `[metadata]` | App ID, version, title, author |
| `[build]` | Build commands, packages |
| `[run]` | Start command, runtime setup |
| `[env]` | Default environment variables |
| `[port]` | Port mappings |
| `[healthcheck]` | Health monitoring |
| `[backup]` | Automated backup config |
| `[[provider]]` | Required services (postgres, redis) |

### Precedence

1. `hop3.toml` values **override** Procfile
2. Non-conflicting values are **merged**
3. You can use both together

---

## Common Workflows

### Deploy a New App

```bash
# 1. Create project with hop3.toml or Procfile
cd myapp

# 2. Initialize hop3 (first time)
hop3 init --ssh root@hop3.example.com

# 3. Deploy (app-name is required)
hop3 deploy myapp

# 4. Check status
hop3 app:status myapp
```

### Update an Existing App

```bash
# 1. Make code changes
# 2. (Optional) Create backup first
hop3 backup:create myapp

# 3. Deploy
hop3 deploy myapp

# 4. If something breaks, restore
hop3 backup:restore <backup-id>
hop3 app:restart myapp
```

### Add a Database

```bash
# 1. Create the addon
hop3 addons:create postgres myapp-db

# 2. Attach to app (sets DATABASE_URL)
hop3 addons:attach myapp-db --app myapp

# 3. Restart to pick up new env var
hop3 app:restart myapp
```

### Debug a Problem

```bash
# Check app status
hop3 app:status myapp

# View logs
hop3 app:logs myapp

# Build logs
hop3 app:build-logs myapp

# Full debug info
hop3 app:debug myapp

# Check environment
hop3 config:show myapp
```

### Scale for Traffic

```bash
# Scale web workers
hop3 ps:scale myapp web=4

# Add background workers
hop3 ps:scale myapp worker=2
```

---

## Best Practices

### Configuration

- **Don't hardcode secrets** in `hop3.toml` or Procfile
- Use `hop3 config:set` for sensitive values (API keys, passwords)
- Keep `hop3.toml` in version control (without secrets)
- Use `[env]` for non-sensitive defaults only

### Deployment

- **Back up before deploying** to production: `hop3 backup:create <app>`
- Test locally first when possible
- Use `--dry-run` when available
- Check logs after deploy: `hop3 app:logs <app>`

### Backups

- Enable automated backups for production:
  ```toml
  [backup]
  enabled = true
  schedule = "0 2 * * *"  # Daily at 2 AM
  retention = 7           # Keep 7 days
  ```
- Test restore procedures periodically

### Environment Variables

- Restart after changing config: `hop3 app:restart <app>`
- Use consistent naming: `DATABASE_URL`, `REDIS_URL`, `SECRET_KEY`
- Keep production and development configs separate

### Working with Multiple Servers

- **Mark production as protected:** `hop3 context add production --server ... --protected`
- **Use environment variable for safety:** `export HOP3_CONTEXT=staging` in your shell
- **Per-project contexts:** Use `hop3 context use <name> --local` for project directories
- **Avoid global context switches:** Don't use `--global` for production contexts
- **Create shell aliases:**
  ```bash
  alias hop3-prod='HOP3_CONTEXT=production hop3'
  alias hop3-staging='HOP3_CONTEXT=staging hop3'
  ```

### Process Management

- Start with `web=1`, scale as needed
- Monitor with `hop3 app:logs` and `hop3 app:status`
- Use health checks to catch failures early

---

## Quick Heroku → Hop3 Translation

| Heroku | Hop3 |
|--------|------|
| `heroku create` | `hop3 app:launch <repo> <name>` |
| `git push heroku main` | `hop3 deploy` |
| `heroku config:set` | `hop3 config:set` |
| `heroku addons:create heroku-postgresql` | `hop3 addons:create postgres` |
| `heroku logs -t` | `hop3 app:logs` |
| `heroku ps` | `hop3 ps` |
| `heroku restart` | `hop3 app:restart` |
| `heroku destroy` | `hop3 app:destroy` |

---

## Getting Help

```bash
# Built-in help
hop3 help
hop3 help --all
hop3 <command> --help

# Documentation
# https://github.com/abilian/hop3

# Issues
# https://github.com/abilian/hop3/issues
```
