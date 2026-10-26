# Hop3 Cheat Sheet

This page is a quick reference for Hop3 users.

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

## Quick Reference: Commands

### Setup & Authentication

```bash
# First time: initialize connection and create admin
hop3 init --ssh root@hop3.example.com

# Log in to existing server
hop3 login root@hop3.example.com

# Check who you're logged in as
hop3 auth whoami

# Get version
hop3 version
```

### Contexts (devel / staging / …)

A context is a server you can reach, named in your own `~/.config/hop3-cli/config.toml`. The examples on this page use `devel` as the context name; name your own whatever you like. Be careful which one a command targets: the context is the only thing standing between a test command and a live server.

```bash
# Name a server (a login does it too: `hop3 login --context devel root@devel.example.com`)
hop3 context add devel   --server ssh://root@devel.example.com
hop3 context add staging --server https://staging.example.com --bootstrap ssh://root@staging.example.com

# Where a command here goes, and why; then the known contexts
hop3 context
hop3 context list

# Inside a project: bind this checkout (writes the gitignored .hop3-local.toml)
cd myproject/
hop3 context use devel

# Outside a project: set the global current context (or --global from inside one)
hop3 context use --global staging

# Remove the binding (or, outside a project, the global current context)
hop3 context unset

# Override for one shell
export HOP3_CONTEXT=devel

# Override for one command (works for any command)
hop3 -c staging app list

# Remove a context
hop3 context remove old-staging
```

Inside a project (a directory with a `hop3.toml` at or above where you stand), a checkout with no binding is refused by every command that reaches a server: run `hop3 context use <name>` once, or pass `-c <name>`. Each such command prints where it goes on stderr, e.g. `→ devel (ssh://root@devel.example.com), bound in this checkout`.

**Context priority (highest to lowest):**

1. `--context` / `-c` flag
2. `HOP3_CONTEXT` (or `HOP3_API_URL`, which names the context `env`)
3. Inside a project: the checkout's binding (`.hop3-local.toml`, written by `hop3 context use`)
4. Outside a project: the global current context (`[cli].default_context`)

What differs per deployment (the app name, its domains, its env) lives in the project's `hop3.toml`, in a `[contexts.<name>]` block keyed by context name; see the [configuration reference](../reference/config.md#contextsname-per-deployment-settings). There is no `--server` flag.

### Application Lifecycle

```bash
# Create app from git repository
hop3 app create <git-url> --app <app-name>

# Deploy (from project directory)
hop3 deploy --app <app-name>

# Deploy from a specific directory
hop3 deploy --app <app-name> /path/to/app

# Check status
hop3 app status --app <app>

# View logs
hop3 app logs --app <app>

# Build logs
hop3 app build-logs --app <app>

# Start / Stop / Restart
hop3 app start --app <app>
hop3 app stop --app <app>
hop3 app restart --app <app>

# List all apps
hop3 app list

# Destroy app (requires confirmation)
hop3 app destroy --app <app>

# Scriptable destroy: no prompt, still safe
hop3 app destroy --app oldapp --confirm=oldapp
```

The app target is the `--app` flag. When an app is resolvable from the current shell or directory (see "Sticky App" below), you can omit `--app` entirely.

### Sticky App (implicit --app)

Most app-scoped commands don't need `--app` if one is resolvable from the current shell or directory.

```bash
# Pin an app for this directory (writes .hop3-app)
hop3 use myapp
hop3 app logs          # no positional needed
hop3 app restart
hop3 env show

# Or set for a single shell
export HOP3_APP=myapp

# Or drop a .hop3-app file in your project
echo myapp > .hop3-app

# Debug the chain
hop3 --why logs
```

The resolution order is `--app` → `$HOP3_APP` → `.hop3-app` → `hop3.toml [cli].app`. See [CLI Reference: App Resolution](../reference/cli.md#app-resolution).

### Configuration / Environment

```bash
# View all env vars
hop3 env show --app <app>

# Get single var
hop3 env get --app <app> VAR_NAME

# Set vars (one or multiple)
hop3 env set --app <app> VAR1=value1 VAR2=value2

# Remove var
hop3 env unset --app <app> VAR_NAME

# Live runtime config
hop3 env live --app <app>

# Migrate Procfile to hop3.toml
hop3 app migrate procfile /path/to/app --dry-run
```

(`config` is the back-compat alias for the `env` command group: `hop3 env show --app <app>` is equivalent.)

### Addons (Backing Services)

```bash
hop3 addon list                           # List instances
hop3 addon types                     # List addon types you can create
hop3 addon create postgres my-db     # Create addon
hop3 addon attach my-db --app <app>  # Attach (sets DATABASE_URL)
hop3 addon detach my-db --app <app>  # Detach from app
hop3 addon show my-db                # Addon info
hop3 addon destroy my-db             # Destroy addon
```

See [CLI Reference: Services](../reference/cli.md#services-addons) for complete documentation.

### Backups

```bash
hop3 backup create --app <app>     # Create backup
hop3 backup list --app <app>       # List backups for an app (bare `backup list` lists all)
hop3 backup show <backup-id>       # Backup details (alias: backup info)
hop3 backup restore <backup-id>    # Restore
hop3 app restart --app <app>       # Restart after restore
hop3 backup destroy <backup-id>    # Delete backup
```

See [Backup and Restore Guide](backup-restore.md) for complete documentation.

### Process Scaling

```bash
# View processes
hop3 ps --app <app>

# Scale (web=2, worker=1)
hop3 ps scale --app <app> web=2 worker=1
```

### System & Admin

```bash
# Facts about this server (version, host, IPs, uptime)
hop3 system info

# Server health report (services, addons, disk, certs)
hop3 system status

# Server logs
hop3 system logs

# User management (admin only)
hop3 user list
hop3 user add <username> <email> --password-file ./pw.txt
hop3 user set-password <username> --stdin   # pipe new password in
hop3 user disable <username>
hop3 user enable <username>
hop3 user set-role <username> <role>   # member, viewer, deployer, admin
hop3 user grant-admin <username>
hop3 user remove <username> --confirm=<username>
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

## CLI Flags

| Flag | Effect |
|------|--------|
| `--json` | JSON output (for scripting; includes `error.exit_code`) |
| `--quiet` / `-q` | Suppress non-essential output |
| `--verbose` / `-v` | More detail (stackable: `-vv` = debug) |
| `-y` / `--yes` / `--force` | Skip confirmations |
| `--confirm=<name>` | Scriptable typed-name confirmation (safer than `--yes`) |
| `--no-input` | Refuse to prompt; fail fast with a hint |
| `--context <name>` / `-c` | Select the target context for this command (no `--server` flag) |
| `--app <name>` / `-a` | Override the resolved app |
| `--why` | Print app/context/alias resolution trace to stderr |
| `--no-alias` | Bypass the alias table (run the typed command literally) |
| `--help` / `-h` | Show help |

### Exit codes (ADR 036 D16)

| Code | Meaning |
|------|---------|
| `0`   | Success |
| `1`   | Generic error |
| `2`   | Usage / syntax error |
| `3`   | Resolution error (app / context not found) |
| `4`   | Authentication |
| `5`   | Authorization |
| `6`   | Conflict (already exists) |
| `7`   | Network / server error |
| `8`   | Deployment failure |
| `9`   | Plugin error |
| `10`  | Confirmation declined or non-tty blocked |
| `130` | Interrupted (SIGINT) |

### Scripting examples

```bash
# Get app state in JSON (with structured exit-code on error)
hop3 app status --app myapp --json | jq '.data.state'

# Safer scripted destroy: typed-name match + still runs safety checks
hop3 app destroy --app myapp --confirm=myapp

# CI: refuse to block on prompts; fail fast with instructions
hop3 user add alice alice@ex.com --password-file ./pw --no-input

# Distinguish "user declined" from other failures
hop3 app destroy --app myapp
case $? in
  0)  echo "destroyed" ;;
  10) echo "declined or non-tty" ;;
  3)  echo "no such app" ;;
  *)  echo "other error" ;;
esac
```

### Helpful diagnostics

<!-- lint-cli-ignore: `hop3 deplo` is an intentional typo demonstrating did-you-mean -->

```bash
# Why did the CLI pick that app / context?
hop3 --why logs

# What aliases are active?
hop3 aliases

# What commands were meant? (Levenshtein suggestion)
hop3 deplo --app myapp   # -> "Did you mean 'deploy'?"
```

## Configuration Files

### Procfile (Simple / Heroku-compatible)

The file lives at `Procfile` in the project root.

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

The file lives at `hop3.toml` in the project root (or `src/hop3.toml`).

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
LOG_LEVEL = "info"

[port]
web = 8000

[healthcheck]
path = "/health/"
timeout = 30
interval = 60
retries = 3

[backup]
paths = ["data"]
exclude = ["*.tmp"]

[[addons]]
type = "postgres"
```

### Key Sections

| Section | Purpose |
|---------|---------|
| `[metadata]` | App ID, version, title, author |
| `[build]` | Build commands, toolchain/builder, packages |
| `[run]` | Start command, `before-run`, `[run.workers]` |
| `[env]` | Default environment variables |
| `[port]` | Port mappings |
| `[healthcheck]` | Health monitoring (`path`/`interval`/`timeout`/`retries`) |
| `[backup]` | Backup `paths` / `exclude` selection |
| `[[addons]]` | Backing services (postgres, mysql, redis, s3) |

See [hop3.toml Reference](../reference/config.md) for complete documentation.

### Precedence

1. `hop3.toml` values **override** Procfile
2. Non-conflicting values are **merged**
3. You can use both together

## Common Workflows

### Deploy a New App

```bash
# 1. Create project with hop3.toml or Procfile
cd myapp

# 2. Initialize hop3 (first time)
hop3 init --ssh root@hop3.example.com

# 3. Deploy
hop3 deploy --app myapp

# 4. Check status
hop3 app status --app myapp
```

### Update an Existing App

```bash
# 1. Make code changes
# 2. (Optional) Create backup first
hop3 backup create --app myapp

# 3. Deploy
hop3 deploy --app myapp

# 4. If something breaks, restore
hop3 backup restore <backup-id>
hop3 app restart --app myapp
```

### Add a Database

```bash
# 1. Create the addon
hop3 addon create postgres myapp-db

# 2. Attach to app (sets DATABASE_URL)
hop3 addon attach myapp-db --app myapp

# 3. Restart to pick up new env var
hop3 app restart --app myapp
```

### Debug a Problem

```bash
# Check app status
hop3 app status --app myapp

# View logs
hop3 app logs --app myapp

# Build logs
hop3 app build-logs --app myapp

# Full debug info
hop3 app debug --app myapp

# Check environment
hop3 env show --app myapp
```

### Scale for Traffic

```bash
# Scale web workers
hop3 ps scale --app myapp web=4

# Add background workers
hop3 ps scale --app myapp worker=2
```

## Best Practices

### Configuration

- **Don't hardcode secrets** in `hop3.toml` or Procfile
- For app-internal random secrets (`SECRET_KEY`, `APP_KEY`, …), declare `KEY = { generate = "hex", length = 32 }` in `[env]`; Hop3 generates once on first deploy, persists, and never commits the value
- Use `hop3 env set` for externally-supplied secrets (API keys, passwords)
- Keep `hop3.toml` in version control (without secrets)
- Use `[env]` for non-sensitive defaults only

### Deployment

- **Back up before deploying** to production: `hop3 backup create --app <app>`
- Test locally first when possible
- Use `--dry-run` when available
- Check logs after deploy: `hop3 app logs --app <app>`

### Backups

- **Back up before deploying** to production: `hop3 backup create --app <app>`
- Select what `hop3 backup create` captures with `[backup]` in `hop3.toml`:
  ```toml
  [backup]
  paths = ["data"]      # Directories to include
  exclude = ["*.tmp"]   # Patterns to skip
  ```
- Test restore procedures periodically
- See [Backup and Restore Guide](backup-restore.md) for scheduling and retention

### Environment Variables

- Restart after changing config: `hop3 app restart --app <app>`
- Use consistent naming: `DATABASE_URL`, `REDIS_URL`, `SECRET_KEY`
- Keep production and development configs separate

### Working with Multiple Environments

- **Name each server once:** `hop3 login --context devel root@devel.example.com` (or `hop3 context add devel --server ssh://root@devel.example.com`). A login without `--context` names the server `default`.
- **Bind each checkout:** `hop3 context use devel` inside the project (writes the gitignored `.hop3-local.toml`); `export HOP3_CONTEXT=devel` for one shell; `-c devel` for one command.
- **Keep per-deployment differences in hop3.toml:** a `[contexts.devel]` block holds that deployment's `app`, `domains` and `env`. Name your contexts alike across the team, so a block means the same deployment for everyone.
- **Project-less commands** (`hop3 app list`, `hop3 system info`) run outside a project go to the global current context, set with `hop3 context use` there (or `--global`).
- **Create shell aliases:**
  ```bash
  alias hop3-devel='HOP3_CONTEXT=devel hop3'
  alias hop3-staging='HOP3_CONTEXT=staging hop3'
  ```

### Process Management

- Start with `web=1`, scale as needed
- Monitor with `hop3 app logs` and `hop3 app status`
- Use health checks to catch failures early

## Quick Heroku → Hop3 Translation

| Heroku | Hop3 |
|--------|------|
| `heroku create` | `hop3 app create <repo> --app <name>` |
| `git push heroku main` | `hop3 deploy` |
| `heroku config set` | `hop3 env set` |
| `heroku addon create heroku-postgresql` | `hop3 addon create postgres` |
| `heroku logs -t` | `hop3 app logs` |
| `heroku ps` | `hop3 ps` |
| `heroku restart` | `hop3 app restart` |
| `heroku destroy` | `hop3 app destroy` |

## Getting Help

```bash
hop3 help              # General help
hop3 help --all        # All commands
hop3 <command> --help  # Help for specific command
```

## Related Guides

- [User Guide](user-guide.md): core concepts and daily operations
- [CLI Reference](../reference/cli.md): complete command documentation
- [hop3.toml Reference](../reference/config.md): full configuration file reference
- [Backup and Restore](backup-restore.md): comprehensive backup documentation
- [Troubleshooting](troubleshooting.md): diagnose and fix common issues
