# Hop3 CLI Reference

**Version:** 0.5.0dev
**Last Updated:** 2026-04-17

This document provides a complete reference for all Hop3 CLI commands.

> **Note (0.5.0 breaking changes).** The CLI surface was redesigned under
> [ADR 036](https://github.com/abilian/hop3/blob/main/notes/adrs/036-cli-ergonomics.md).
> Key changes from 0.4.x:
>
> - Commands use spaces, not colons: `hop3 config set` (was `hop3 config:set`).
> - Implicit `--app` resolution chain with sticky context (`hop3 use <app>`).
> - Alias mechanism: `hop3 apps`, `hop3 env`, `hop3 whoami` are built-in aliases.
> - Did-you-mean suggestions on typos for both commands and app names.
> - 11-code exit-code table (see [Exit Codes](#exit-codes)) and the `--no-input`,
>   `--confirm=<name>`, `--password-file`/`--stdin` flags for automation.
> - State-change summary lines on mutations, routed to stderr for pipeline safety.

---

## Table of Contents

- [Getting Started](#getting-started)
- [Global Flags](#global-flags)
- [Context Management](#context-management)
- [Authentication Commands](#authentication-commands)
- [Application Management](#application-management)
- [Configuration Management](#configuration-management)
- [Nix Commands](#nix-commands)
- [Backup and Restore](#backup-and-restore)
- [Services (Addons)](#services-addons)
- [Admin Commands](#admin-commands)
- [System Commands](#system-commands)
- [Miscellaneous Commands](#miscellaneous-commands)

---

## Getting Started

### Installation

```bash
# Install hop3-cli
pip install hop3-cli

# Or using uv
uv pip install hop3-cli
```

### Configuration

Set your API endpoint and authenticate:

```bash
# Set API endpoint
export HOP3_API_URL="https://your-hop3-server.com"
# or
export HOP3_API_URL="ssh://user@your-hop3-server.com"

# Login
hop3 auth login <username> <password>

# Save token (automatically stored in ~/.hop3/token)
```

### Basic Usage

```bash
# List all applications
hop3 apps

# Deploy an application
hop3 deploy myapp

# View application status
hop3 app status myapp

# View logs
hop3 app logs myapp
```

---

## Global Flags

All commands support these global flags (per ADR 036 D6).
Flags may appear before or after the subcommand.

### Output Formatting

- **`--json`** - Output results in JSON format (machine-readable). Implies non-interactive: no prompts, no colors, no spinners. The JSON envelope includes `error.exit_code` so scripts don't need to map error strings.
- **`--quiet`** - Suppress non-essential output (minimal output). Errors and state-change summaries still print.

### Interaction

- **`-y, --yes`** - Skip confirmation prompts entirely (auto-confirm destructive operations).
- **`--force`** - Override all safety checks. Coarser than `--yes`: required for `app destroy` / `context remove` when dependent resources exist, and bypasses preview and attached-resource warnings.
- **`--confirm=<name>`** - Scriptable alternative to the interactive typed-name prompt. Pass the resource name you're acknowledging; the command runs without prompting *and* preserves other safety checks (context warnings, attached-addon detection). Use in preference to `--force` when you only want to skip the typed-name prompt. Example: `hop3 app destroy myapp --confirm=myapp`.
- **`--no-input`** - Refuse to prompt. If input would be required, the command fails with a one-line instruction naming the flag or env var to use instead. For automation/CI where stdin isn't a terminal. Sets `HOP3_NO_INPUT=1` so prompt-bearing helpers propagate the choice.

### Context and App Selection

- **`-c, --context <name>`** - Use a specific server context for this command only (ADR 036 D8).
- **`-a, --app <name>`** - Target app explicitly. Always a flag, never positional (D5). If not set, the resolver walks the D7 chain — see [App Resolution](#app-resolution) below.

### Diagnostics

- **`--why`** - Print the resolution trace to stderr **and exit** (diagnostic-only — the command is NOT executed). Shows which source supplied `--app`, `--context`, and (if applicable) what the alias resolver did. Safe to use with destructive commands: `hop3 deploy --why` reports the trace without deploying.
- **`--no-alias`** - Bypass alias resolution. `hop3 --no-alias apps` tries `apps` as a literal command rather than expanding the built-in alias to `app list`.

### Verbosity

### Verbosity

Verbosity controls how much output is displayed. The verbosity level is passed to the server and affects all command output.

| Level | Value | Flags | Description |
|-------|-------|-------|-------------|
| Quiet | 0 | `-q`, `--quiet` | Minimal output (errors only) |
| Normal | 1 | (default) | Standard output |
| Verbose | 2 | `-v`, `--verbose` | Detailed output (build logs, command details) |
| Debug | 3 | `-vv`, `--debug` | Maximum verbosity (all internal operations) |

**Flag stacking:** You can use multiple `-v` flags for increased verbosity:
- `-v` = verbose (level 2)
- `-vv` = debug (level 3)
- `-vvv` = debug (capped at level 3)

**Environment variable:** Set `HOP3_VERBOSITY` to control default verbosity:
```bash
export HOP3_VERBOSITY=2  # Default to verbose mode
```

Explicit flags override the environment variable.

### Examples

```bash
# Get JSON output
hop3 apps --json

# Deploy without confirmation
hop3 deploy myapp -y

# Quiet mode (minimal output)
hop3 backup create myapp --quiet

# Verbose deployment (see Docker build output)
hop3 -v deploy myapp

# Debug mode (maximum verbosity)
hop3 -vv deploy myapp
# or
hop3 --debug deploy myapp

# Combine flags
hop3 app destroy oldapp --yes --quiet

# Set default verbosity via environment
HOP3_VERBOSITY=0 hop3 deploy myapp  # Quiet mode

# Scriptable typed-name confirmation (no prompt, but still safe)
hop3 app destroy oldapp --confirm=oldapp

# Non-interactive pipeline: fail fast if a prompt would appear
cat password.txt | hop3 user add alice alice@ex.com --stdin --no-input

# Ask "why did the CLI pick THAT app/context?"
hop3 --why logs
```

### App Resolution

App-scoped commands (like `hop3 logs`, `hop3 restart`, `hop3 config set`)
don't require an explicit app name. The CLI resolves one by walking this
chain in order, stopping at the first source that supplies a value (ADR 036 D7):

1. **`--app <name>` / `-a <name>`** - explicit flag wins over everything else.
2. **`$HOP3_APP`** - environment variable for the current shell session.
3. **`.hop3-app` file** - a one-line file in the current directory or any
   ancestor up to `$HOME`. Put it in a project repo and every `hop3` invocation
   from within picks up the right app.
4. **`hop3.toml [cli].app`** - same search path as `.hop3-app`, lower priority.
5. **`hop3.toml [metadata].id`** - the project's canonical name (same value
   the server uses). The "I'm physically standing in this project" source.
   Outranks the global default so being inside a project always wins over
   a sticky `hop3 use` from another directory.
6. **Active context's `default_app`** - set via `hop3 use <app>`.
7. **Git remote named `hop3`** - reserved for future use.

Set `--why` on any app-scoped command to see the trace:

```bash
hop3 --why logs
# [app resolution] source=.hop3-app -> 'myapp' (from /home/me/project/.hop3-app)
```

**Sticky app:**

```bash
hop3 use myapp        # Bind app 'myapp' to current context as default
hop3 use              # Show current sticky app
hop3 use --clear      # Unbind
```

Once bound, `hop3 logs`, `hop3 restart`, etc. all default to `myapp`
without needing `--app` or positional. A `.hop3-app` file in the CWD
takes precedence.

---

## Context Management

Contexts allow you to manage multiple Hop3 servers (e.g., production, staging, development) safely. Similar to `kubectl` contexts, you can switch between servers without accidentally running commands against the wrong environment.

### Why Use Contexts?

- **Safety**: Prevent accidental production deployments from your development terminal
- **Convenience**: Quickly switch between servers without changing environment variables
- **Protection**: Mark production contexts as "protected" for extra confirmation on destructive operations

### Context Priority

When determining which server to use, the CLI checks these sources in order:

| Priority | Source | Scope |
|----------|--------|-------|
| 1 (highest) | `--context` flag | Single command |
| 2 | `HOP3_CONTEXT` environment variable | Current shell |
| 3 | `.hop3-local.toml [current].context` (ADR 042) | Per project checkout |
| 4 (lowest) | Global config file | All terminals |

### `hop3 context add`

Add a new server context.

**Usage:**
```bash
hop3 context add <name> --server <url> [options]
```

**Arguments:**
- `name` - Context name (e.g., "production", "staging", "dev")
- `--server <url>` - Server URL (required)

**Options:**
- `--token <token>` - API authentication token
- `--protected` - Mark as protected (requires extra confirmation for destructive operations)
- `--ssh-user <user>` - SSH username (default: root)
- `--ssh-port <port>` - SSH port (default: 22)

**Examples:**
```bash
# Add a development context
hop3 context add dev --server ssh://root@dev.example.com

# Add a protected production context
hop3 context add production --server ssh://root@prod.example.com --protected

# Add with token
hop3 context add staging --server https://staging.example.com --token eyJ...
```

**Notes:**
- The first context added automatically becomes the current context
- Protected contexts require typing `context/resource` instead of just `resource` for destructive operations

---

### `hop3 context list`

List all configured contexts.

**Usage:**
```bash
hop3 context list
```

**Example Output:**
```
Configured contexts:

    production [protected]
      Server: ssh://root@prod.example.com
  * staging
      Server: ssh://root@staging.example.com
    dev
      Server: ssh://root@dev.example.com

Current context: staging
```

**Notes:**
- `*` indicates the current context
- `[protected]` indicates contexts that require extra confirmation

---

### `hop3 context current`

Show the current context and where it's configured.

**Usage:**
```bash
hop3 context current
```

**Example Output:**
```
Current context: production
  Source: HOP3_CONTEXT environment variable
  Server: ssh://root@prod.example.com
  Protected: yes (requires confirmation for destructive operations)
```

**Possible sources:**
- `--context flag` - Set via command line
- `HOP3_CONTEXT environment variable` - Set in current shell
- `.hop3-local.toml [current].context` - Set for current project checkout (ADR 042)
- `global config` - Set as global default

---

### `hop3 context use`

Switch to a different context. **Safe by default** - does not modify global config.

**Usage:**
```bash
hop3 context use [--global] <name>
```

**Arguments:**
- `name` - Context name to switch to

**Options:**
- (default) - Print `export` command for this shell only (safest)
- `--global` - Set as global default (**affects all terminals** - use with caution)

Per-project context selection: run `hop3 context use <name>` from inside a project directory (a tree containing `hop3.toml`). The project-scoped verb writes `.hop3-local.toml` and adds it to `.gitignore` automatically (ADR 042).

**Examples:**
```bash
# Print export command (recommended - only affects current shell after you run it)
hop3 context use production
# Output:
# To use context 'production' in this shell, run:
#   export HOP3_CONTEXT=production

# Per-project: stand in the project tree and select a declared context
cd my-staging-project/
hop3 context use staging        # writes .hop3-local.toml

# Set as global default (dangerous - affects ALL terminals)
hop3 context use production --global
```

**Best Practice:**

For production servers, use the environment variable approach:
```bash
# In your .bashrc or .zshrc for production work:
alias hop3-prod='HOP3_CONTEXT=production hop3'

# Or set for current terminal session:
export HOP3_CONTEXT=production
```

---

### `hop3 context remove`

Remove a context.

**Usage:**
```bash
hop3 context remove <name>
```

**Example:**
```bash
hop3 context remove old-staging
```

**Notes:**
- If you remove the current context, another context becomes current (if any exist)
- Does not affect the actual server, only removes the local configuration

---

### Using Contexts

#### Per-Command Context

Use `--context` flag for one-off commands:
```bash
# Deploy to production without changing your current context
hop3 --context production deploy myapp

# Check staging logs while working on dev
hop3 --context staging app logs myapp
```

#### Per-Shell Context

Set environment variable for your terminal session:
```bash
# This terminal is now "production mode"
export HOP3_CONTEXT=production

# All commands use production
hop3 apps
hop3 app status myapp
```

#### Per-Project Context (ADR 042)

Stand in the project directory and run `hop3 context use <name>` — the project-scoped verb writes `.hop3-local.toml` and auto-gitignores it:
```bash
cd my-staging-project/
hop3 context use staging
# Writes .hop3-local.toml with [current].context = "staging"
# Adds .hop3-local.toml to .gitignore if it isn't already

# Now any hop3 command in this directory uses staging
hop3 deploy myapp
```

The legacy single-line `.hop3-context` file (and its `--local` flag) was retired in ADR 042 Step 7. Stale `.hop3-context` files have no effect — re-run `hop3 context use <name>` to migrate to `.hop3-local.toml`.

---

### Protected Contexts

Protected contexts provide an extra safety layer for production environments.

**Setting up a protected context:**
```bash
hop3 context add production --server ssh://root@prod.example.com --protected
```

**What changes with protected contexts:**

1. **Extra confirmation prompt** before any destructive operation
2. **Stricter type-to-confirm** - Must type `context/resource` instead of just `resource`

**Example:**
```bash
$ hop3 --context production app destroy myapp

  WARNING: You are operating on protected context 'production'
  This context is marked as protected to prevent accidental changes.

Are you sure you want to continue with this destructive action? [y/N]: y

WARNING: This will permanently destroy the app 'myapp'.
Type 'production/myapp' to confirm (context/app): production/myapp
✓ App 'myapp' destroyed.
```

---

### Environment Variables

| Variable | Description |
|----------|-------------|
| `HOP3_CONTEXT` | Override the current context for this shell |

**Example `.bashrc` setup:**
```bash
# Production alias with explicit context
alias hop3-prod='HOP3_CONTEXT=production hop3'
alias hop3-staging='HOP3_CONTEXT=staging hop3'

# Or set default for specific terminal profiles
# In your "Production Terminal" profile:
export HOP3_CONTEXT=production
```

---

### Configuration File

Contexts are stored in `~/.config/hop3-cli/config.toml`:

```toml
current_context = "staging"

[contexts.staging]
api_url = "ssh://root@staging.example.com"
api_token = "eyJ..."
protected = false
ssh_user = "root"
ssh_port = 22

[contexts.production]
api_url = "ssh://root@prod.example.com"
api_token = "eyJ..."
protected = true
ssh_user = "root"
ssh_port = 22
```

---

## Authentication Commands

### `hop3 auth register`

Register a new user account.

**Usage:**
```bash
hop3 auth register <username> <email> <password>
```

**Arguments:**
- `username` - Desired username (alphanumeric, underscores, hyphens)
- `email` - Valid email address
- `password` - Password (minimum 8 characters recommended)

**Example:**
```bash
hop3 auth register alice alice@example.com mypassword123
```

**Notes:**
- First registered user automatically becomes admin
- Passwords are hashed with bcrypt (work factor 12)
- Email must be unique

---

### `hop3 auth login`

Authenticate and receive an API token.

**Usage:**
```bash
hop3 auth login <username> <password>
```

**Arguments:**
- `username` - Your username
- `password` - Your password

**Example:**
```bash
hop3 auth login alice mypassword123
```

**Output:**
```
Login successful!
Token: eyJ0eXAiOiJKV1QiLCJhbGc...
Token saved to ~/.hop3/token
```

**Notes:**
- Token stored in `~/.hop3/token` by default
- Token valid for 30 days by default
- Set `HOP3_API_TOKEN` environment variable to override

---

### `hop3 auth whoami`

Display current authenticated user information.

**Usage:**
```bash
hop3 auth whoami
```

**Example Output:**
```
Username: alice
Email: alice@example.com
Roles: admin, user
Active: Yes
```

---

### `hop3 auth logout`

Logout and invalidate current token.

**Usage:**
```bash
hop3 auth logout
```

**Notes:**
- Removes token from `~/.hop3/token`
- Token remains valid until expiration unless server-side revocation implemented

---

## Application Management

### `hop3 apps`

List all applications.

**Usage:**
```bash
hop3 apps [--json]
```

**Example Output:**
```
┌─────────────────────────────────────────────────────────────┐
│ Applications                                                 │
├────────────┬────────────┬──────────────────────┬────────────┤
│ Name       │ Status     │ URL                  │ Deployed   │
├────────────┼────────────┼──────────────────────┼────────────┤
│ myapp      │ RUNNING    │ https://myapp.com    │ 2 days ago │
│ testapp    │ STOPPED    │ https://test.app.com │ 1 week ago │
└────────────┴────────────┴──────────────────────┴────────────┘
```

**JSON Output:**
```json
{
  "apps": [
    {
      "name": "myapp",
      "status": "RUNNING",
      "url": "https://myapp.com",
      "deployed_at": "2025-11-10T14:30:00Z"
    }
  ]
}
```

---

### `hop3 app launch`

Create and configure a new app from a Git repository.

**Usage:**
```bash
hop3 app launch <repo_url> <app_name>
```

**Arguments:**
- `repo_url` - Git repository URL (HTTPS or SSH)
- `app_name` - Name for the application (alphanumeric, hyphens, underscores)

**Example:**
```bash
hop3 app launch https://github.com/user/myapp.git myapp
```

**Notes:**
- Clones repository to server
- Does not deploy automatically (use `hop3 deploy` after launch)
- Repository must be accessible from server

---

### `hop3 deploy`

Deploy an application from uploaded source or configured repository.

**Usage:**
```bash
hop3 deploy <app_name> [options] [directory]
```

**Arguments:**
- `app_name` - Name of application to deploy
- `directory` - Source directory (default: current directory)

**Options:**
- `--env KEY=VALUE` or `-e KEY=VALUE` - Set environment variable (can be repeated)
- `--no-stream` - Disable real-time log streaming (use batch output)
- `--stream` - Enable real-time log streaming (default)

**Examples:**
```bash
# Deploy from current directory
cd myapp/
hop3 deploy myapp

# Deploy with environment variables
hop3 deploy myapp --env LOG_LEVEL=info --env MAX_WORKERS=4

# Deploy from specific directory
hop3 deploy myapp ./src

# Disable streaming (batch output at end)
hop3 deploy myapp --no-stream
```

**Real-time Log Streaming:**

By default, `hop3 deploy` streams deployment logs in real-time via Server-Sent Events (SSE). You'll see build output as it happens:

```
> Starting deployment for app 'myapp'
-> Using builder: 'LocalBuilder'
--> Creating virtualenv...
--> Installing from requirements.txt
    Collecting Flask==3.0.0
    Successfully installed Flask-3.0.0
-> Build successful
-> Using deployment strategy: 'uwsgi'
> Waiting for app 'myapp' to start (timeout: 600s)...
> App 'myapp' is now running.

✓ Deployment completed successfully in 45.2s
```

Use `--no-stream` to fall back to batch output (all logs shown at end).

**Process:**
1. Uploads source code as tarball
2. Extracts on server
3. Detects language/framework (Python, Node.js, Ruby, Go, Static)
4. Builds application (installs dependencies, compiles assets)
5. Configures reverse proxy (nginx, Caddy, or Traefik)
6. Starts application processes

**Startup Timeout:**

Apps must start within a configurable timeout (default: 10 minutes). Configure per-app in `hop3.toml`:

```toml
[run]
start-timeout = 900  # 15 minutes
```

Or set server-wide default via `APP_START_TIMEOUT` environment variable.

**Notes:**
- Requires `Procfile` or `hop3.toml` for process configuration
- Automatically detects buildpack based on files present
- Use `-v` or `-vv` for more verbose output (see [Global Flags](#global-flags))
- Build logs are also saved and can be retrieved with `app build-logs`
- Streaming requires direct HTTP connection (SSH tunnel falls back to batch mode)
- See [Packaging Applications](../guides/packaging-applications.md) for details

---

### `hop3 app status`

Show detailed status of an application.

**Usage:**
```bash
hop3 app status <app_name>
```

**Example Output:**
```
Application: myapp
Status: RUNNING
Hostname: myapp.example.com
Port: 8000

Processes:
  web: 2 running
  worker: 1 running

Memory Usage: 245 MB
Uptime: 3 days 14 hours
```

---

### `hop3 app logs`

Show application logs.

**Usage:**
```bash
hop3 app logs <app_name> [--lines N] [--follow]
```

**Arguments:**
- `app_name` - Name of application

**Options:**
- `--lines N` - Number of lines to show (default: 100)
- `--follow` or `-f` - Follow log output (real-time)

**Example:**
```bash
# Show last 100 lines
hop3 app logs myapp

# Show last 500 lines
hop3 app logs myapp --lines 500

# Follow logs in real-time
hop3 app logs myapp --follow
```

---

### `hop3 app build-logs`

Show build logs for an application (Docker build output).

**Usage:**
```bash
hop3 app build-logs <app_name>
```

**Arguments:**
- `app_name` - Name of application

**Example:**
```bash
# Show build logs for myapp
hop3 app build-logs myapp
```

**Example Output:**
```
=== Docker Build Log ===
Timestamp: 2025-12-09 14:30:22
App: myapp
Status: SUCCESS
Duration: 45.3s

=== STDOUT ===
#1 [internal] load build definition from Dockerfile
#2 [internal] load .dockerignore
#3 [1/5] FROM debian:bookworm-slim
...

=== STDERR ===
```

**Notes:**
- Shows the most recent Docker build output
- Useful for debugging deployment failures
- Logs are stored in `{app_path}/log/build.log`
- Use `deploy -v` or `deploy --debug` to see output during deployment

---

### `hop3 app restart`

Restart an application.

**Usage:**
```bash
hop3 app restart <app_name>
```

**Example:**
```bash
hop3 app restart myapp
```

**Notes:**
- Graceful restart (waits for requests to complete)
- Reloads environment variables
- Zero-downtime for apps with multiple processes

---

### `hop3 app start`

Start a stopped application.

**Usage:**
```bash
hop3 app start <app_name>
```

---

### `hop3 app stop`

Stop a running application.

**Usage:**
```bash
hop3 app stop <app_name>
```

**Notes:**
- Gracefully stops all processes
- Application remains configured (can be restarted)

---

### `hop3 app debug`

Show comprehensive debug information for an application.

**Usage:**
```bash
hop3 app debug <app_name>
```

**Notes:**
- Collects environment, logs, process status, and configuration
- Useful for troubleshooting deployment issues

---

### `hop3 app env`

Show environment variables with their sources.

**Usage:**
```bash
hop3 app env <app_name>
```

**Notes:**
- Shows where each variable comes from (hop3.toml, config set, addon, etc.)
- Useful for debugging configuration issues

---

### `hop3 app ping`

Check if an application is responding to HTTP requests.

**Usage:**
```bash
hop3 app ping <app_name>
```

**Notes:**
- Performs HTTP health check on the application
- Returns response status and time

---

### `hop3 app destroy` ⚠️

**DESTRUCTIVE** - Destroy an app, removing all files and configuration.

**Usage:**
```bash
hop3 app destroy <app_name>
```

**Confirmation Required:**
```
WARNING: This will permanently delete the app 'myapp' and all its data.
Type the app name to confirm: myapp
```

**What Gets Deleted:**
- All source code
- All data in `/data` directory
- All environment variables
- All attached services (credentials removed)
- All backups
- Reverse proxy configuration

**Skip Confirmation:**
```bash
hop3 app destroy myapp --yes
```

**⚠️ WARNING:** This operation is irreversible. Always backup before destroying.

---

## Configuration Management

### `hop3 config show`

Show all environment variables for an app.

**Usage:**
```bash
hop3 config show <app_name>
```

**Example Output:**
```
Environment Variables for myapp:

DATABASE_URL=postgresql://user:pass@localhost/db
REDIS_URL=redis://localhost:6379
SECRET_KEY=***hidden***
LOG_LEVEL=info
```

**Notes:**
- Sensitive values masked by default
- Use `config get` to retrieve specific values

---

### `hop3 config get`

Get a specific environment variable value.

**Usage:**
```bash
hop3 config get <app_name> <KEY>
```

**Example:**
```bash
hop3 config get myapp DATABASE_URL
# Output: postgresql://user:pass@localhost/db
```

---

### `hop3 config set`

Set environment variables for an app.

**Usage:**
```bash
hop3 config set <app_name> KEY1=value1 [KEY2=value2 ...]
```

**Arguments:**
- `app_name` - Name of application
- `KEY=value` - One or more key-value pairs

**Examples:**
```bash
# Set single variable
hop3 config set myapp LOG_LEVEL=info

# Set multiple variables
hop3 config set myapp \
  DATABASE_URL=postgresql://localhost/db \
  REDIS_URL=redis://localhost:6379 \
  SECRET_KEY=mysecret

# Set variable with spaces (quote the value)
hop3 config set myapp MESSAGE="Hello World"
```

**Notes:**
- Requires app restart to take effect: `hop3 app restart myapp`
- Values are stored encrypted in database
- No leading/trailing whitespace in keys

---

### `hop3 config unset`

Unset (remove) environment variables for an app.

**Usage:**
```bash
hop3 config unset <app_name> KEY1 [KEY2 ...]
```

**Arguments:**
- `app_name` - Name of application
- `KEY` - One or more keys to remove

**Examples:**
```bash
# Remove single variable
hop3 config unset myapp DEBUG

# Remove multiple variables
hop3 config unset myapp OLD_KEY DEPRECATED_VAR UNUSED_SECRET
```

---

### `hop3 config live`

Show live runtime environment of running app.

**Usage:**
```bash
hop3 config live <app_name>
```

**Notes:**
- Shows environment as currently loaded by running processes
- Useful for debugging configuration issues

---

### `hop3 config migrate`

Migrate configuration from other PaaS formats to `hop3.toml`.

**Usage:**
```bash
hop3 config migrate [--format heroku|flyio|procfile] [--dry-run] [--backup]
```

**Options:**
- `--format` - Source format (heroku, flyio, procfile)
- `--dry-run` - Preview without writing file
- `--backup` - Create backup of existing hop3.toml

**Example:**
```bash
# Migrate Procfile to hop3.toml
cd myapp/
hop3 config migrate --format procfile --dry-run

# Apply migration with backup
hop3 config migrate --format procfile --backup
```

---

## Domain Management

Manage the hostnames bound to an app. These commands are a first-class view
over the `HOST_NAME` env var that the reverse-proxy plugins
(nginx / caddy / traefik) read. All write operations are atomic: every
hostname is validated and conflicts with other apps are checked up front
before anything is persisted. After every write you must redeploy
(`hop3 deploy <app>`) for the proxy configuration to be updated.

For the declarative equivalent in `hop3.toml`, see
[`[domains]`](./config.md#domains-application-hostnames).

### `hop3 domains list`

Show the hostnames currently bound to an app.

**Usage:**
```bash
hop3 domains list <app>
hop3 domains list --app <app>
```

**Example:**
```bash
hop3 domains list abilian-cms
```

---

### `hop3 domains add`

Add one or more hostnames to an app (union, atomic, deduplicated).

**Usage:**
```bash
hop3 domains add <app> <host> [<host> ...]
hop3 domains add --app <app> <host> [<host> ...]
```

**Example:**
```bash
hop3 domains add abilian-cms fermigier.com www.fermigier.com \
                              abilian.com www.abilian.com
```

---

### `hop3 domains remove`

Remove one or more hostnames from an app. Errors if any of the requested
hostnames is not currently bound.

**Usage:**
```bash
hop3 domains remove <app> <host> [<host> ...]
hop3 domains remove --app <app> <host> [<host> ...]
```

---

### `hop3 domains set`

Replace the full list of hostnames bound to an app.

**Usage:**
```bash
hop3 domains set <app> <host> [<host> ...]
hop3 domains set --app <app> <host> [<host> ...]
```

**Example:**
```bash
hop3 domains set abilian-cms abilian.com www.abilian.com
```

---

### `hop3 domains clear`

Clear all hostnames from an app (unsets `HOST_NAME`).

**Usage:**
```bash
hop3 domains clear <app>
hop3 domains clear --app <app>
```

---

## Nix Commands

### `hop3 nix eject`

Materialize the auto-generated `hop3.nix` from a `[nix]` template
config into a real `hop3.nix` file in the app's source directory.
After ejection, the NixBuilder uses the committed `hop3.nix` instead
of regenerating from the template, and the `[nix]` section in
`hop3.toml` is ignored.

Use `nix eject` when you've outgrown the templates and need to
customise the generated Nix expression directly.

**Usage:**
```bash
hop3 nix eject <app-name>
```

**Behavior:**
- Reads the `[nix]` section from the app's `hop3.toml`
- Generates the Nix expression using the same template engine that
  the NixBuilder uses at deploy time
- Writes the result as `hop3.nix` in the app's source directory,
  with a header noting which template it came from and the date
- Refuses to overwrite an existing `hop3.nix`

**Example:**
```bash
# Eject the generated Nix for the "myapp" deployment
hop3 nix eject myapp

# Inspect the result
cat /path/to/myapp-source/hop3.nix

# Edit it freely — the [nix] section in hop3.toml is now ignored
```

**Errors:**
- "App has no hop3.toml" — the app source has no `hop3.toml`
- "No `[nix]`.template in hop3.toml" — the app isn't using template mode
- "hop3.nix already exists" — remove the existing file first if you
  want to re-eject

**See also:**
- [Nix deployment guide](../guides/nix-deployment.md)
- [hop3.toml `[nix]` section](config.md#nix-template-based-nix-builds)

---

## Backup and Restore

### `hop3 backup create`

Create a backup of an application.

**Usage:**
```bash
hop3 backup create <app_name> [--description "text"]
```

**Arguments:**
- `app_name` - Name of application to backup

**Options:**
- `--description` - Optional description for the backup

**Example:**
```bash
hop3 backup create myapp --description "Before major upgrade"
```

**What Gets Backed Up:**
- Application source code (git archive if available)
- Data directory (`/data`)
- Environment variables
- Attached services (database dumps, etc.)

**Output:**
```
Creating backup for myapp...
├─ Backing up source code... ✓
├─ Backing up data directory... ✓
├─ Backing up environment variables... ✓
└─ Backing up services (postgres: myapp-db)... ✓

Backup created: backup-myapp-20251112-143022
Location: /home/hop3/.hop3/backups/backup-myapp-20251112-143022.tar.gz
Size: 45.2 MB
```

**See Also:** [Backup and Restore Guide](../guides/backup-restore.md)

---

### `hop3 backup list`

List all backups, optionally filtered by application.

**Usage:**
```bash
hop3 backup list [app_name]
```

**Examples:**
```bash
# List all backups
hop3 backup list

# List backups for specific app
hop3 backup list myapp
```

**Example Output:**
```
┌───────────────────────────────────────────────────────────────────┐
│ Backups for myapp                                                 │
├─────────────────────────────┬──────────┬───────────────┬──────────┤
│ Backup ID                   │ Size     │ Created       │ Services │
├─────────────────────────────┼──────────┼───────────────┼──────────┤
│ backup-myapp-20251112-14302 │ 45.2 MB  │ 2 hours ago   │ postgres │
│ backup-myapp-20251110-09153 │ 43.1 MB  │ 2 days ago    │ postgres │
└─────────────────────────────┴──────────┴───────────────┴──────────┘
```

---

### `hop3 backup info`

Show detailed information about a backup.

**Usage:**
```bash
hop3 backup info <backup_id>
```

**Example Output:**
```
Backup Information

Backup ID: backup-myapp-20251112-143022
Application: myapp
Created: 2025-11-12 14:30:22 UTC (2 hours ago)
Size: 45.2 MB
Description: Before major upgrade

Contents:
├─ Source code: 2.1 MB (git commit: abc123f)
├─ Data directory: 15.3 MB (145 files)
├─ Environment variables: 12 variables
└─ Services:
   └─ postgres (myapp-db): 27.8 MB

Checksums (SHA256):
├─ source.tar.gz: 3f7a8b2c...
├─ data.tar.gz: 9d4e1a5f...
└─ services/postgres-myapp-db.sql: 7c2b9e4a...
```

---

### `hop3 backup restore`

Restore an application from a backup.

**Usage:**
```bash
hop3 backup restore <backup_id> [--app new_app_name]
```

**Arguments:**
- `backup_id` - ID of backup to restore

**Options:**
- `--app` - Restore to different app name (default: original app name)

**Examples:**
```bash
# Restore to original app (overwrites existing)
hop3 backup restore backup-myapp-20251112-143022

# Restore to new app name
hop3 backup restore backup-myapp-20251112-143022 --app myapp-restored
```

**Process:**
1. Creates application if it doesn't exist
2. Restores source code
3. Restores data directory
4. Restores environment variables
5. Restores services (databases, etc.)
6. Verifies checksums

**Notes:**
- Does not automatically start the app (use `hop3 app start`)
- Restoring to existing app overwrites data (confirmation required)

---

### `hop3 backup destroy` ⚠️

**DESTRUCTIVE** - Delete a backup.

**Usage:**
```bash
hop3 backup destroy <backup_id>
```

**Confirmation Required:**
```
WARNING: This will permanently delete the backup 'backup-myapp-20251112-143022'.
Type 'DELETE' to confirm: DELETE
```

**Skip Confirmation:**
```bash
hop3 backup destroy backup-myapp-20251112-143022 --yes
```

---

## Services (Addons)

Services are backing infrastructure (databases, caches, queues) that can be attached to applications.

### `hop3 addon create`

Create a new backing service instance.

**Usage:**
```bash
hop3 addon create <service_type> <service_name>
```

**Arguments:**
- `service_type` - Type of service (postgres, redis, etc.)
- `service_name` - Name for this service instance

**Example:**
```bash
hop3 addon create postgres myapp-db
```

**Output:**
```
Service 'myapp-db' of type 'postgres' created successfully.

To attach this service to an app, run:
  hop3 addon attach myapp-db --app <app-name>
```

**Notes:**
- Service created but not yet attached to any app
- Credentials generated and stored encrypted
- Use `addon attach` to connect to an application

---

### `hop3 addon attach`

Attach a service to an application.

**Usage:**
```bash
hop3 addon attach <service_name> --app <app_name> [--service-type <type>]
```

**Arguments:**
- `service_name` - Name of service to attach
- `--app` - Name of application

**Options:**
- `--service-type` - Service type (default: postgres)

**Example:**
```bash
hop3 addon attach myapp-db --app myapp --service-type postgres
```

**Output:**
```
Service 'myapp-db' attached to app 'myapp' successfully.

Environment variables:
  Added DATABASE_URL
  Added DB_USER
  Added DB_PASSWORD
  Added DB_NAME

Restart your app for changes to take effect:
  hop3 app restart myapp
```

**What Happens:**
- Service connection details added as environment variables
- Credentials stored encrypted in database
- App must be restarted to use new variables

---

### `hop3 addon detach`

Detach a service from an application.

**Usage:**
```bash
hop3 addon detach <service_name> --app <app_name> [--service-type <type>]
```

**Example:**
```bash
hop3 addon detach myapp-db --app myapp
```

**Notes:**
- Removes environment variables from app
- Does not destroy the service itself
- Credentials removed from app

---

### `hop3 addon destroy` ⚠️

**DESTRUCTIVE** - Destroy a service instance.

**Usage:**
```bash
hop3 addon destroy <service_name> [--service-type <type>]
```

**Warning:**
```
WARNING: This will permanently delete all data in service 'myapp-db'!
Type the service name to confirm: myapp-db
```

**What Gets Deleted:**
- All data in the service (database, cache, etc.)
- All credentials across all apps
- Service configuration

**Notes:**
- Service must be detached from all apps first (or use `--force`)
- Backups are NOT automatically created (use `backup create` first)

---

### `hop3 addon show`

Get information about a service instance.

**Usage:**
```bash
hop3 addon show <service_name> [--service-type <type>]
```

**Example Output:**
```
Service: myapp-db
Type: postgres

Status: Running
Version: PostgreSQL 14.5
Size: 127 MB
Tables: 15
Connections: 3 active
```

---

### `hop3 addon list`

List addon instances (aliased to `hop3 addons`).

**Usage:**
```bash
hop3 addon list [--type <type>]
```

**Options:**
- `--type` - Filter by addon type (postgres, mysql, redis)

**Example:**
```bash
# List all addon types
hop3 addon list

# List PostgreSQL addons
hop3 addon list --type postgres
```

---

### `hop3 addon status`

Show detailed status and health of an addon.

**Usage:**
```bash
hop3 addon status <service_name> [--type <type>]
```

**Notes:**
- Shows connection status, health checks, and resource usage
- More detailed than `addon show`

---

## Admin Commands

Admin commands require admin role. First user registered automatically gets admin role.

### `hop3 user list`

List all user accounts.

**Usage:**
```bash
hop3 user list
```

**Example Output:**
```
┌────────────────────────────────────────────────────────────┐
│ Users                                                      │
├──────────┬───────────────────────┬────────────┬───────────┤
│ Username │ Email                 │ Roles      │ Status    │
├──────────┼───────────────────────┼────────────┼───────────┤
│ alice    │ alice@example.com     │ admin,user │ Active    │
│ bob      │ bob@example.com       │ user       │ Active    │
│ charlie  │ charlie@example.com   │ user       │ Disabled  │
└──────────┴───────────────────────┴────────────┴───────────┘
```

---

### `hop3 user add`

Create a new user account.

**Usage:**
```bash
hop3 user add <username> <email> <password>
```

---

### `hop3 user show`

Display detailed information about a user.

**Usage:**
```bash
hop3 user show <username>
```

---

### `hop3 user set-password`

Reset a user's password.

**Usage:**
```bash
hop3 user set-password <username> <new_password>
```

---

### `hop3 user disable`

Disable a user account (prevents login).

**Usage:**
```bash
hop3 user disable <username>
```

---

### `hop3 user enable`

Enable a disabled user account.

**Usage:**
```bash
hop3 user enable <username>
```

---

### `hop3 user remove`

Remove a user account.

**Usage:**
```bash
hop3 user remove <username>
```

---

### `hop3 user grant-admin`

Grant admin privileges to a user.

**Usage:**
```bash
hop3 user grant-admin <username>
```

---

### `hop3 user revoke-admin`

Revoke admin privileges from a user.

**Usage:**
```bash
hop3 user revoke-admin <username>
```

---

### `hop3 user generate-token`

Generate a new API token for a user (bootstrap helper).

**Usage:**
```bash
hop3 user generate-token <username>
```

**Example Output:**
```
Token generated for user 'alice':
eyJ0eXAiOiJKV1QiLCJhbGc...
```

**Notes:**
- Useful for CI/CD or automated scripts
- Token does not expire by default (set expiration in config)

---

## System Commands

Four subcommands answer four distinct questions about the server:

| Command | Answers |
|---|---|
| `system status` | *Is the server OK?* — full health report + identity header |
| `system info` | *What is this server?* — static facts (version, OS, IPs) |
| `system logs` | *What happened?* — server log tail with filters |
| `system cleanup` | *Reclaim Docker resources* — networks, images, build cache |

The pre-0.5 commands `system check`, `system uptime`, and `system ps` were removed: `check` was renamed to `status` (it was always the rich health view), `uptime` is now part of the `status` and `info` identity header, and `ps` returned the entire host's process table over RPC and was removed as a security smell. For per-app process info, use `hop3 app processes <app>`.

---

### `hop3 system status`

Show full health status of the Hop3 server. Default output: one-line identity header (host, IP, version, uptime) followed by per-section health items, then a bottom-line summary.

**Usage:**
```bash
hop3 system status [--quiet|-q] [--json]
```

**Options:**
- `--quiet`, `-q` — One-line summary only. For scripts.
- `--json` — Machine-readable JSON. For dashboards and external monitors.

**Exit code:** non-zero when there is any warning or failure (the command emits an `error`/`warning` response item).

**Example output:**
```
Hop3 server: hop3-dev (135.181.203.156) — v0.5.0.dev3 — up 14d 3h

Services
  Hop3 Server      ✓ running
  Nginx            ✓ running
  uWSGI Emperor    ✓ running

Backing services
  PostgreSQL       ✓ ok
  MySQL            ✓ ok
  Redis            ⚠ unreachable — connection refused (127.0.0.1:6379)
  S3 (minio)       ✓ ok

Filesystem
  HOP3_ROOT        ✓ writable
  Apps directory   ✓ writable
  Disk usage       ⚠ 86%

Certificates
  SSL              ⚠ self-signed (Let's Encrypt not configured)

Status: ⚠ 2 warnings
```

Severity legend: `✓` ok · `⚠` warning · `✗` failure. Optional services (Redis, Docker) report `⚠` when unreachable rather than `✗` so the overall status stays *degraded* rather than *failed*.

---

### `hop3 system info`

Show static facts about this server. No liveness probes — for "is everything OK?", use `system status`.

**Usage:**
```bash
hop3 system info [--verbose|-v]
```

**Options:**
- `--verbose`, `-v` — Also list loaded plugins (builders, deployers, toolchains) and key filesystem paths.

**Example output:**
```
Version:        0.5.0.dev3
Python:         3.12.3
Platform:       Linux 6.8.0-117-generic
Hostname:       hop3-dev
IP Addresses:   135.181.203.156
Uptime:         14d 3h
Docker:         installed
```

---

### `hop3 system logs`

Show Hop3 server logs from the default log file, with optional time-window, level, and regex filters.

**Usage:**
```bash
hop3 system logs [-n N] [--since DURATION] [--level LEVEL] [--grep PATTERN]
```

**Options:**
- `-n`, `--lines N` — Number of lines to show (default: 100).
- `--since DURATION` — Show logs since a duration ago (e.g. `1h`, `30m`, `1d`).
- `--level LEVEL` — Filter by log level (`DEBUG`, `INFO`, `WARNING`, `ERROR`).
- `--grep PATTERN` — Filter lines matching a regex (case-insensitive).

---

### `hop3 system cleanup`

Reclaim unused Docker resources: stopped containers, unused networks, dangling images, build cache.

**Usage:**
```bash
hop3 system cleanup [--dry-run] [--all] [--volumes]
```

**Options:**
- `--dry-run` — Show what would be cleaned without doing it.
- `--all` — Also remove unused images (not just dangling).
- `--volumes` — Also prune unused volumes. *May cause data loss.*

---

## Miscellaneous Commands

### `hop3 help`

Display help information.

**Usage:**
```bash
hop3 help [command]
hop3 help --all          # Flat index of every command, with markers
hop3 help --all -v       # Full help for every command, aggregated
```

**Examples:**
```bash
# General help
hop3 help

# Help for specific command
hop3 help deploy
hop3 help backup create

# Flat alphabetical index of every command (top-level + namespaced)
hop3 help --all

# One long document aggregating the full help for every command,
# recursively (server commands + client-side local commands). Handy for
# piping to a file or a pager:
hop3 help --all -v | less
hop3 help --all --verbose > hop3-commands.txt
```

---

### `hop3 help commands`

Return list of available command names for shell completion.

**Usage:**
```bash
hop3 help commands
```

**Notes:**
- Returns plain text list of command names
- Used internally by shell completion scripts

---

### `hop3 completion`

Generate shell completion scripts.

**Usage:**
```bash
hop3 completion <shell>
```

**Arguments:**
- `shell` - Shell type: `bash`, `zsh`, or `fish`

**Installation Examples:**
```bash
# Bash (current session)
eval "$(hop3 completion bash)"

# Bash (permanent)
hop3 completion bash > /etc/bash_completion.d/hop3

# Zsh
hop3 completion zsh > ~/.zsh/completions/_hop3

# Fish
hop3 completion fish > ~/.config/fish/completions/hop3.fish
```

**Options:**
- `--refresh` - Update cached command list from server
- `--status` - Show cache status

---

### `hop3 plugins`

List installed plugins and their commands.

**Usage:**
```bash
hop3 plugins
```

---

### `hop3 ps`

Show process count for an app.

**Usage:**
```bash
hop3 ps <app_name>
```

---

### `hop3 ps scale`

Set the process count for an app.

**Usage:**
```bash
hop3 ps scale <app_name> web=N [worker=M ...]
```

**Example:**
```bash
# Scale web processes to 3, worker processes to 2
hop3 ps scale myapp web=3 worker=2
```

---

### `hop3 run`

Run a command in the context of an app.

**Usage:**
```bash
hop3 run <app_name> <command>
```

**Examples:**
```bash
# Run database migrations
hop3 run myapp python manage.py migrate

# Open interactive shell
hop3 run myapp python manage.py shell

# Run one-off script
hop3 run myapp node scripts/cleanup.js
```

---

### `hop3 app sbom`

Generate a Software Bill of Materials (SBOM) for an app.

**Usage:**
```bash
hop3 app sbom <app_name>
```

**Output:**
- CycloneDX format JSON
- Lists all dependencies with versions
- Security scanning metadata

---

## Exit Codes

The Hop3 CLI uses the exit-code table defined in ADR 036 D16. Scripts can
distinguish user error from server error from "user said no" without parsing
messages.

| Code | Meaning |
|------|---------|
| `0`   | Success (including empty results) |
| `1`   | Generic error (fallback) |
| `2`   | Usage / syntax error (invalid arguments, malformed flags) |
| `3`   | Resolution error (app or context not found) |
| `4`   | Authentication error (not logged in, token expired) |
| `5`   | Authorization error (forbidden, permission denied) |
| `6`   | Conflict (resource already exists, locked, in use) |
| `7`   | Network / server error (connection, timeout, 5xx) |
| `8`   | Deployment failure |
| `9`   | Plugin error |
| `10`  | Confirmation declined or non-tty blocked |
| `130` | Interrupted (SIGINT / Ctrl-C) |

JSON output (`--json`) includes `error.exit_code` in the envelope so
programmatic consumers don't have to mirror this mapping.

**Script tip.** Code `10` is your friend: use it to distinguish a user
typing "no" at a confirmation prompt from an actual operation failure.
Non-interactive scripts should pass `--confirm=<name>` or `--yes` to avoid
it altogether, or `--no-input` to fail fast with an actionable message
instead of hanging.

---

## Environment Variables

### Configuration

- **`HOP3_API_URL`** - Server URL (http://server or ssh://user@server)
- **`HOP3_API_TOKEN`** - API authentication token (overrides ~/.hop3/token)
- **`HOP3_CONTEXT`** - Use a specific server context (see [Context Management](#context-management))
- **`HOP3_CONFIG_DIR`** - Config directory (default: ~/.hop3)
- **`HOP3_VERBOSITY`** - Default verbosity level (0=quiet, 1=normal, 2=verbose, 3=debug)
- **`HOP3_APP`** - Sticky app name for the current shell session (app-resolution chain, ADR 036 D7)
- **`HOP3_NO_INPUT`** - When set to `1`, interactive prompts are refused with an actionable error. Set automatically when `--no-input` is passed; can be set manually to propagate through subprocesses.

### Security

- **`HOP3_SECRET_KEY`** - Encryption key for credentials (server-side, required in production)
- **`HOP3_UNSAFE`** - Disable authentication (⚠️ NEVER use in production, test-only)

### Development

- **`HOP3_DEBUG`** - Enable debug logging
- **`HOP3_DEV_HOST`** - Development server target for testing

---

## Tips and Best Practices

### Security

1. **Never use** `HOP3_UNSAFE` **in production** - This completely disables authentication
2. **Protect your token** - Store `~/.hop3/token` with `chmod 600`
3. **Rotate tokens regularly** - Use `auth logout` and `auth login` to refresh
4. **Backup HOP3_SECRET_KEY** - Required to decrypt service credentials
5. **Use SSH connections** - Preferred over HTTP for remote servers

### Workflow

1. **Always backup before destructive operations:**
   ```bash
   hop3 backup create myapp --description "Before destroy"
   hop3 app destroy myapp --yes
   ```

2. **Use `--dry-run` when available:**
   ```bash
   hop3 config migrate --dry-run  # Preview changes first
   ```

3. **Check status before and after operations:**
   ```bash
   hop3 app status myapp
   hop3 app restart myapp
   hop3 app status myapp  # Verify restart
   ```

4. **Use `--json` for automation:**
   ```bash
   apps=$(hop3 apps --json | jq -r '.apps[].name')
   for app in $apps; do
     hop3 backup create "$app"
   done
   ```

### Confirmation Prompts

Destructive commands require confirmation:
- **Type the resource name** - For `app destroy`, type the app name
- **Type 'DELETE'** - For `backup destroy` and `services destroy`
- **Skip with `-y`** - Use `--yes` flag to auto-confirm (use carefully!)

**Example:**
```bash
$ hop3 app destroy myapp
WARNING: This will permanently delete the app 'myapp' and all its data.
Type the app name to confirm: myapp
✓ App 'myapp' destroyed successfully.
```

---

## Getting Help

### Command-specific Help

```bash
hop3 help <command>
hop3 <command> --help
```

### Documentation

- **User Guide:** [Quickstart](../get-started/quickstart.md)
- **Backup Guide:** [Backup and Restore](../guides/backup-restore.md)
- **Migration Guide:** [CLI Migration](../guides/cli-migration.md)

### Community

- **GitHub Issues:** https://github.com/abilian/hop3/issues
- **Documentation:** https://docs.hop3.cloud

---

**Last Updated:** 2026-02-13
**CLI Version:** 0.4.0
**Server Version:** 0.4.0
