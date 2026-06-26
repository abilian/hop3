# Hop3 CLI Reference

**Version:** 0.6.0
**Last Updated:** 2026-04-17

This document provides a complete reference for all Hop3 CLI commands.

> **Note (0.5.0 breaking changes).** The CLI surface was redesigned under
> [ADR 036](/developers/adrs/036-cli-ergonomics/).
> Key changes from 0.4.x:
>
> - Commands use spaces, not colons: `hop3 env set` (was `hop3 config:set`).
> - Implicit `--app` resolution chain with sticky context (`hop3 use <app>`).
> - Alias mechanism: `hop3 apps`, `hop3 addons`, `hop3 plugins`, `hop3 whoami` are built-in aliases (`env` is a real command group, with `config` as its back-compat alias).
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
- [Environment Variables](#environment-variables)
- [Domain Management](#domain-management)
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
# One-liner installer (recommended)
curl -LsSf https://hop3.cloud/install-cli.py | python3 -

# Or from PyPI
pip install hop3-cli

# Or as an isolated uv tool
uv tool install hop3-cli
```

### Configuration

Set your API endpoint and authenticate:

```bash
# Set API endpoint
export HOP3_API_URL="https://your-hop3-server.com"
# or
export HOP3_API_URL="ssh://user@your-hop3-server.com"

# Login (interactive; stores the token in the per-server credential store)
hop3 login            # short form of `hop3 auth login`

# The token is stored in the per-server credential store
# ~/.config/hop3-cli/credentials.toml (or override with HOP3_API_TOKEN)
```

### Basic Usage

```bash
# List all applications
hop3 apps

# Deploy an application
hop3 deploy --app myapp

# View application status
hop3 app status --app myapp

# View logs
hop3 app logs --app myapp
```

---

## Global Flags

All commands support these global flags (per ADR 036 D6). Flags may appear before or after the subcommand.

### Output Formatting

- **`--json`** - Output results in JSON format (machine-readable). Implies non-interactive: no prompts, no colors, no spinners. The JSON envelope includes `error.exit_code` so scripts don't need to map error strings.
- **`--quiet`** - Suppress non-essential output (minimal output). Errors and state-change summaries still print.

### Interaction

- **`-y, --yes`** - Skip confirmation prompts entirely (auto-confirm destructive operations).
- **`--force`** - Override all safety checks. Coarser than `--yes`: required for `app destroy` / `context remove` when dependent resources exist, and bypasses preview and attached-resource warnings.
- **`--confirm=<name>`** - Scriptable alternative to the interactive typed-name prompt. Pass the resource name you're acknowledging; the command runs without prompting *and* preserves other safety checks (context warnings, attached-addon detection). Use in preference to `--force` when you only want to skip the typed-name prompt. Example: `hop3 app destroy --app myapp --confirm=myapp`.
- **`--no-input`** - Refuse to prompt. If input would be required, the command fails with a one-line instruction naming the flag or env var to use instead. For automation/CI where stdin isn't a terminal. Sets `HOP3_NO_INPUT=1` so prompt-bearing helpers propagate the choice.

### Context and App Selection

- **`-c, --context <name>`** - Select the target context for this command — the **one selector** for every command, app-bound or not (ADR 042). Resolves project-first (`hop3.toml [contexts.<name>]`) then global (`config.toml [contexts.<name>]`); an explicit `--context` that resolves to nothing aborts loud. There is no `--server` flag.
- **`-a, --app <name>`** - Target app explicitly. Always a flag, never positional (D5). If not set, the resolver walks the D7 chain — see [App Resolution](#app-resolution) below.

### Diagnostics

- **`--why`** - Print the resolution trace to stderr **and exit** (diagnostic-only — the command is NOT executed). Shows which source supplied `--app`, `--context`, and (if applicable) what the alias resolver did. Safe to use with destructive commands: `hop3 deploy --why` reports the trace without deploying.
- **`--no-alias`** - Bypass alias resolution. `hop3 --no-alias apps` tries `apps` as a literal command rather than expanding the built-in alias to `app list`.

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
hop3 deploy --app myapp -y

# Quiet mode (minimal output)
hop3 backup create --app myapp --quiet

# Verbose deployment (see Docker build output)
hop3 -v deploy --app myapp

# Debug mode (maximum verbosity)
hop3 -vv deploy --app myapp
# or
hop3 --debug deploy --app myapp

# Combine flags
hop3 app destroy --app oldapp --yes --quiet

# Set default verbosity via environment
HOP3_VERBOSITY=0 hop3 deploy --app myapp  # Quiet mode

# Scriptable typed-name confirmation (no prompt, but still safe)
hop3 app destroy --app oldapp --confirm=oldapp

# Non-interactive pipeline: fail fast if a prompt would appear
cat password.txt | hop3 user add alice alice@ex.com --stdin --no-input

# Ask "why did the CLI pick THAT app/context?"
hop3 --why logs
```

### App Resolution

App-scoped commands (like `hop3 app logs`, `hop3 app restart`, `hop3 env set`) don't require an explicit app name. The CLI resolves one by walking this chain in order, stopping at the first source that supplies a value (ADR 036 D7):

1. **`--app <name>` / `-a <name>`** - explicit flag wins over everything else.
2. **`$HOP3_APP`** - environment variable for the current shell session.
3. **`.hop3-app` file** - a one-line file in the current directory or any
   ancestor up to `$HOME`. Put it in a project repo and every `hop3` invocation
   from within picks up the right app.
4. **`hop3.toml [cli].app`** - same search path as `.hop3-app`, lower priority.
5. **`hop3.toml [metadata].id`** - the project's canonical name (same value
   the server uses). The "I'm physically standing in this project" fallback,
   used when no higher-priority source (`.hop3-app`, `[cli].app`) is set in
   this directory tree.
6. **Git remote named `hop3`** - reserved for future use.

Set `--why` on any app-scoped command to see the trace:

```bash
hop3 --why logs
# [app resolution] source=.hop3-app -> 'myapp' (from /home/me/project/.hop3-app)
```

**Sticky app:**

```bash
hop3 use myapp        # Pin app 'myapp' for this directory (writes .hop3-app)
hop3 use              # Show the currently pinned app
hop3 use --clear      # Remove the .hop3-app pin
```

`hop3 use <app>` writes a `.hop3-app` file in the current directory (item 3 of the
[App Resolution](#app-resolution) chain). Once pinned, `hop3 app logs`,
`hop3 app restart`, etc. all default to `myapp` from within that directory tree
without needing `--app` or a positional argument.

---

## Context Management

A **context** is a named target — **`--context <name>` is the one selector for every command** (ADR 042), app-bound or not. A context exists at two scopes:

- **Project** — declared in your project's committed `hop3.toml` under `[contexts.<name>]`: a full deploy environment, a non-secret bundle of `server` (a literal address like `ssh://root@host`), `app` (the app *instance* name for that environment), domains, and non-secret env. One codebase, many environments — each a distinct app instance, often on a different server.
- **Global** — declared in your per-developer `config.toml` as `[contexts.<name>].server`: just a name bound to a server address. It exists so project-less commands can target a server by name — `hop3 apps --context prod` — exactly like an in-project deploy.

`--context <name>` resolves **project-first, then global**: the nearest `hop3.toml [contexts.<name>]`, else `config.toml [contexts.<name>]`. An explicit `--context` that resolves to nothing aborts loud — it never silently retargets a different instance. There is no `--server` flag: naming the target is the context's job.

A context is **not** a server-connection record: bearer tokens never live in `hop3.toml` or `config.toml`. They live in the per-server credential store (`~/.config/hop3-cli/credentials.toml`), populated by `hop3 login`/`hop3 init`.

### Why Use Contexts?

- **Multi-environment**: Express `dev` / `staging` / `prod` as distinct app instances in one committed file, shared with your team.
- **One selector everywhere**: `--context` targets both app-bound commands (`hop3 deploy --context prod`) and project-less ones (`hop3 apps --context prod`) — nothing to remember about which flag applies where.
- **Safety**: A context names its own app (`myapp-prod` vs `myapp-dev`), so deploys go where you mean — surfaced by the deploy preview and the project-mismatch guard.
- **No secrets in the repo**: contexts carry only addresses and non-secret config; tokens and secret env stay out of `hop3.toml` and `config.toml`.

### Context Priority

The CLI resolves which context *name* to use by checking these sources in order, stopping at the first that supplies one:

| Priority | Source | Scope |
|----------|--------|-------|
| 1 (highest) | `--context <name>` / `-c <name>` flag | Single command |
| 2 | `HOP3_CONTEXT` environment variable | Current shell |
| 3 | `.hop3-local.toml [local].context` (written by `hop3 context use`, gitignored) | Per project checkout |
| 4 (lowest) | Single-context fallback (project: exactly one `[contexts.*]` in `hop3.toml`) / `[cli].default_context` (project-less) | Per project / per developer |

The chosen name then resolves to a context **project-first, then global**. If nothing supplies a context, app-scoped commands report *"no context; run `hop3 context use <name>` or pass `--context`"*; project-less commands fall back through `[cli].default_context` → the legacy unnamed `[cli].default_server` → the sole known server.

### `hop3 context add`

Add a context. The scope follows where you stand: inside a project it adds a
deploy environment (`[contexts.<name>]`) to the committed `hop3.toml`; outside a
project (or with `--global`/`-g`) it adds a **global** context — a named server —
to your per-developer `config.toml`. Contexts are **non-secret** in both files:
the server is a literal address, never a token.

**Usage:**
```bash
hop3 context add <name> --server <addr> [--app <app>] [--domain <d>]... [--env K=V]...
hop3 context add <name> --server <addr> [--global]   # global: server only
```

**Arguments / options:**
- `name` - Context name (e.g., "dev", "staging", "prod")
- `--server <addr>` - Target server address (required), e.g. `ssh://root@host`
- `--app <app>` - App instance name (project only; inherits `[metadata].id`)
- `--domain <host>` - Hostname for this environment (project only, repeatable)
- `--env KEY=VALUE` - Non-secret env override (project only, repeatable)
- `--global` / `-g` - Force the global scope (`config.toml`), even inside a project. A global context is just a named server — `--app` / `--domain` / `--env` are project-only and rejected here.

**Examples:**
```bash
# A dev and a prod environment in this project's hop3.toml
hop3 context add dev  --server ssh://root@dev.example.com  --app myapp-dev
hop3 context add prod --server ssh://root@prod.example.com --app myapp --domain myapp.com

# A global named server (run outside a project, or with --global inside one),
# so `hop3 apps --context prod` works with no project:
hop3 context add prod --server ssh://root@prod.example.com
hop3 context add prod --server ssh://root@prod.example.com --global
```

**Notes:**
- Inside a project, writes the committed `hop3.toml` — commit it to share the environment with your team. Outside a project (or with `--global`), writes the per-developer `config.toml` (secret-free).
- To *log in* to a server (store its token), use `hop3 login` — `hop3 login --context prod --ssh root@host` also names the global context and makes it the default. To *select* a project environment for this checkout, use `hop3 context use <name>`.
- Secrets never go here — set per-environment secrets server-side with `hop3 env set`.

---

### `hop3 context list`

List contexts at the current scope. Inside a project it lists the `[contexts.*]` declared in the nearest `hop3.toml`, marking the one selected for this checkout. Outside a project (or with `--global`) it lists the **global** contexts from `config.toml`, marking the default.

**Usage:**
```bash
hop3 context list
```

**Example Output (in a project):**
```
Contexts in /home/me/project/hop3.toml:

    prod
      server: ssh://root@prod.example.com
      app:    myapp
      domains: myapp.com
  * staging
      server: ssh://root@staging.example.com
      app:    myapp-staging
    dev
      server: ssh://root@dev.example.com

Selected (this checkout): staging
```

**Example Output (project-less, global):**
```
Global contexts (config.toml):

  * prod
      server: ssh://root@prod.example.com
    staging
      server: ssh://root@staging.example.com

Default context: prod
Select one with `--context <name>` on any command.
```

**Notes:**
- In a project, `*` indicates the context selected for this checkout (via `.hop3-local.toml`).
- Outside a project, `*` indicates the default context (`[cli].default_context`).
- Pass `--global` to list the global contexts even from inside a project tree.

---

### `hop3 context show`

Show one context — by name, or the one currently selected. Inside a project it reads the project `hop3.toml` block; outside a project (or with `--global`) it reads the global context from `config.toml` (where, with no name, it shows the default context).

**Usage:**
```bash
hop3 context show [<name>]
```

**Example Output (project):**
```
Context: prod
  server:  ssh://root@prod.example.com
  app:     myapp
  domains: myapp.com, www.myapp.com
  env:     LOG_LEVEL
```

**Example Output (project-less, global):**
```
Context: prod (default)  [global]
  server:  ssh://root@prod.example.com
```

**Possible selection sources** (highest to lowest):
- `--context <name>` / `-c <name>` - Set via command line
- `HOP3_CONTEXT environment variable` - Set in current shell
- `.hop3-local.toml [local].context` - Pinned for this checkout (`hop3 context use`)
- Single-context fallback (project) / `[cli].default_context` (project-less)

---

### `hop3 context use`

Pin a context for this checkout. **Safe by default** — writes a gitignored `.hop3-local.toml`, never the committed `hop3.toml` and never global state.

**Usage:**
```bash
hop3 context use <name>
```

**Arguments:**
- `name` - Name of a context declared in this project's `hop3.toml`

Run `hop3 context use <name>` from inside a project directory (a tree containing `hop3.toml`). It writes `[local].context = "<name>"` to `.hop3-local.toml` (item 3 of the [Context Priority](#context-priority) chain). The file is local and not committed — each checkout chooses its own environment. `use` pins a *project* context only — it has no global form; to set a global default target, log in naming it (`hop3 login --context <name>`) or select per-command with `--context <name>`.

**Examples:**
```bash
# Stand in the project tree and select a declared context
cd my-staging-project/
hop3 context use staging        # writes .hop3-local.toml [local].context = "staging"

# Now any hop3 command in this directory tree targets the staging environment
hop3 deploy
```

**Best Practice:**

For one-off commands against another environment, prefer the per-command flag or the env var over re-pinning:
```bash
# One command against production, without changing this checkout's selection:
hop3 --context prod deploy

# Or make a whole terminal session "production mode":
export HOP3_CONTEXT=prod
```

---

### `hop3 context remove`

Remove a context at the current scope: a `[contexts.<name>]` block from the project's `hop3.toml` inside a project, or a global context from `config.toml` outside one (or with `--global`).

**Usage:**
```bash
hop3 context remove <name>
```

**Example:**
```bash
hop3 context remove old-staging
```

**Notes:**
- In a project, edits the committed `hop3.toml` — commit the change to share it with your team. Outside a project, edits the per-developer `config.toml` (and clears `[cli].default_context` if it pointed here).
- Does not affect the actual server, only the context declaration
- If this checkout still selects the removed project context (via `.hop3-local.toml`), re-point it with `hop3 context use <other>`

---

### `hop3 context rename`

Rename a `[contexts.<old>]` block to `[contexts.<new>]` in the project's `hop3.toml`.

**Usage:**
```bash
hop3 context rename <old> <new>
```

**Notes:**
- Edits the committed `hop3.toml` — commit the change to share it
- If this checkout selected the old name, its `.hop3-local.toml` pin is re-pointed to the new name automatically

---

### Using Contexts

#### Per-Command Context

Use `--context` flag for one-off commands:
```bash
# Deploy to production without changing your current context
hop3 --context production deploy --app myapp

# Check staging logs while working on dev
hop3 --context staging app logs --app myapp
```

#### Per-Shell Context

Set environment variable for your terminal session:
```bash
# This terminal is now "production mode"
export HOP3_CONTEXT=production

# All commands use production
hop3 apps
hop3 app status --app myapp
```

#### Per-Project Context (ADR 042)

Stand in the project directory and run `hop3 context use <name>` — the project-scoped verb writes `.hop3-local.toml` and auto-gitignores it:
```bash
cd my-staging-project/
hop3 context use staging
# Writes .hop3-local.toml with [local].context = "staging"
# Adds .hop3-local.toml to .gitignore if it isn't already

# Now any hop3 command in this directory uses staging
hop3 deploy --app myapp
```

The legacy single-line `.hop3-context` file (and its `--local` flag) was retired in ADR 042 Step 7. Stale `.hop3-context` files have no effect — re-run `hop3 context use <name>` to migrate to `.hop3-local.toml`.

---

### Destructive-operation safety

Destructive verbs (`app destroy`, `config set`, …) always require confirmation —
there is no per-context "protected" flag in ADR 042 (a context is non-secret
config, not a managed connection). Two layers guard you:

- The **deploy preview** shows the resolved app, server and domains before a
  deploy, so you can see exactly where it's going.
- The **project-mismatch guard** refuses a destructive op when the resolved app
  doesn't match the project you're standing in *and* the app came from a non-
  CWD-rooted source (an ambient `$HOP3_CONTEXT`, an ancestor overlay) — pass
  `--force` to override.

**Example:**
```bash
$ hop3 app destroy --app myapp

WARNING: This will permanently destroy the app 'myapp'.
Type 'myapp' to confirm: myapp
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

### Files and where things live (ADR 042)

A context lives at two scopes: a **project** environment in your committed `hop3.toml`, and a **global** named server in your per-developer `config.toml`. Both files are secret-free — tokens live in a separate credential store. The four files that matter:

| File | Scope | Holds | Secret? |
|------|-------|-------|---------|
| `hop3.toml` | committed, shared | **project** `[contexts.<name>]` environments (`server`, `app`, domains, env) + base app config | no |
| `~/.config/hop3-cli/credentials.toml` | per-developer | bearer tokens keyed by server address | **yes** (local) |
| `~/.config/hop3-cli/config.toml` | per-developer | CLI preferences + **global** `[contexts.<name>].server` (named servers) + `[cli].default_context` | no |
| `.hop3-local.toml` (gitignored) | per-checkout | `[local].context` — which project environment this checkout targets | no |

**Contexts in `hop3.toml`** (committed, no secrets):

```toml
[metadata]
id = "myapp"

[contexts.staging]
server = "ssh://root@staging.example.com"
app    = "myapp-staging"
[contexts.staging.domains]
list = ["staging.myapp.com"]
[contexts.staging.env]
LOG_LEVEL = "debug"

[contexts.prod]
server = "ssh://root@prod.example.com"
app    = "myapp"
[contexts.prod.domains]
list = ["myapp.com", "www.myapp.com"]
[contexts.prod.env]
LOG_LEVEL = "warning"
```

**Credential store** (`~/.config/hop3-cli/credentials.toml`) — local, per-developer, secret. Bearer tokens keyed by the *canonical* server address. Written only by `hop3 login` / `hop3 init`, created `0o600` (parent dir `0o700`); you never edit it by hand:

```toml
[servers."ssh://root@prod.example.com:22"]
token = "eyJ..."

[servers."ssh://root@staging.example.com:22"]
token = "eyJ..."
```

**Global config** (`~/.config/hop3-cli/config.toml`) — secret-free. Local preferences plus **global contexts** (named servers) and the default context used by project-less commands (`hop3 apps`). The token still lives only in the credential store:

```toml
[cli]
default_context = "prod"                         # used by `hop3 apps` etc. with no --context
# default_server = "ssh://root@host"             # legacy unnamed fallback (lower priority)

[contexts.prod]
server = "ssh://root@prod.example.com"           # a named server — `--context prod` anywhere

[contexts.staging]
server = "ssh://root@staging.example.com"
```

So `hop3 apps --context prod` targets the named server with no project; a bare `hop3 apps` targets `[cli].default_context`.

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

Log in to a server. `hop3 login` is the short form of this command.

This is the interactive, full-featured login: it supports SSH bootstrap, token
URLs, magic links (`--web`) and password entry, and it stores the resulting
token in the per-server credential store (`credentials.toml`). It also makes that
server the default target for project-less commands. Pass `--context <name>` to
**name** that server as a global context (`config.toml`) and make it the default
context in one step — so `hop3 apps --context <name>` works afterwards with no
project. It takes no positional username/password — for a non-interactive,
scriptable token use [`hop3 auth get-token`](#hop3-auth-get-token).

**Usage:**
```bash
hop3 login                                  # password (prompted) for the default server
hop3 login --ssh root@server                # SSH bootstrap (no password needed)
hop3 login --context prod --ssh root@server # SSH bootstrap; also names global context 'prod' + default
hop3 login --token <tok> --url <url>        # pre-generated token + server address
hop3 login --web                            # magic link for the web dashboard
```

**Notes:**
- Token stored in the per-server credential store (`~/.config/hop3-cli/credentials.toml`), keyed by the server address; that server becomes the default target
- With `--context <name>`, the server is also recorded as a global context in `config.toml` and set as `[cli].default_context` — secret-free; the token still lives only in the credential store
- Token valid for 30 days by default
- Set `HOP3_API_TOKEN` environment variable to override

---

### `hop3 auth get-token`

Verify credentials and **print** an API token — for scripts and automation. It
does not save anything; capture the token yourself. Pass the password without
putting it on the command line.

**Usage:**
```bash
hop3 auth get-token <username> --password-file -    # read password from stdin
hop3 auth get-token <username> --password-file pw   # read password from a file
```

**Example:**
```bash
TOKEN=$(printf '%s' "$HOP3_PASSWORD" | hop3 auth get-token alice --password-file -)
```

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
- Revokes the token on the server, then removes it from the per-server credential store (`~/.config/hop3-cli/credentials.toml`)
- If the server can't be reached to revoke, the local token is still cleared and the revoke failure is surfaced loudly

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
│ Applications                                                │
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

### `hop3 app create`

Create and configure a new app from a Git repository. `hop3 app launch` is a back-compat alias.

**Usage:**
```bash
hop3 app create <repo_url> --app <app_name>
```

**Arguments:**
- `repo_url` - Git repository URL (HTTPS or SSH)
- `--app <app_name>` - Name for the application (alphanumeric, hyphens, underscores)

**Example:**
```bash
hop3 app create https://github.com/user/myapp.git --app myapp
```

**Notes:**
- Clones repository to server
- Does not deploy automatically (use `hop3 deploy` afterwards)
- Repository must be accessible from server

---

### `hop3 deploy`

Deploy an application from uploaded source or configured repository.

**Usage:**
```bash
hop3 deploy [--app <app_name>] [options] [directory]
```

**Arguments:**
- `--app <app_name>` - Name of application to deploy (else resolved from context)
- `directory` - Source directory (default: current directory)

**Options:**
- `--env KEY=VALUE` or `-e KEY=VALUE` - Set environment variable (can be repeated)
- `--no-stream` - Disable real-time log streaming (use batch output)
- `--stream` - Enable real-time log streaming (default)

**Examples:**
```bash
# Deploy from current directory (app from context)
cd myapp/
hop3 deploy --app myapp

# Deploy with environment variables
hop3 deploy --app myapp --env LOG_LEVEL=info --env MAX_WORKERS=4

# Deploy from a specific directory
hop3 deploy --app myapp ./src

# Disable streaming (batch output at end)
hop3 deploy --app myapp --no-stream
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
> Waiting for app 'myapp' to start (timeout: 60s)...
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

Apps must start within a configurable timeout (server default: 60 seconds). Configure per-app in `hop3.toml`:

```toml
[run]
start-timeout = 900  # 15 minutes
```

Or change the server-wide default via the `APP_START_TIMEOUT` environment variable.

**Notes:**
- A `hop3.toml` configures the build and runtime; the detected toolchain supplies a default process model, so most apps deploy without any process file
- Automatically detects the toolchain based on files present
- Use `-v` or `-vv` for more verbose output (see [Global Flags](#global-flags))
- Build logs are also saved and can be retrieved with `app build-logs`
- Streaming requires direct HTTP connection (SSH tunnel falls back to batch mode)
- See [Packaging Applications](../guides/packaging-applications.md) for details

---

### `hop3 app status`

Show detailed status of an application. `hop3 status` is a top-level alias.

**Usage:**
```bash
hop3 app status [--app <app>]
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
hop3 app logs [--app <app>] [-n N] [--grep PATTERN] [--since-deploy] [--build]
```

**Options:**
- `--app <app>` - Target application (else resolved from context)
- `-n N`, `--lines N` - Number of lines to show (default: 100)
- `--grep PATTERN` - Show only lines containing PATTERN (case-insensitive substring)
- `--since-deploy` - Show only logs since the last deployment
- `--build` - Show build logs instead of runtime logs (equivalent to `app build-logs`)

**Example:**
```bash
# Show last 100 lines (app from context)
hop3 app logs

# Show last 500 lines for an explicit app
hop3 app logs --app myapp -n 500

# Filter to lines containing 'error'
hop3 app logs --app myapp --grep error

# Only logs since the last deploy
hop3 app logs --app myapp --since-deploy
```

---

### `hop3 app build-logs`

Show build logs for an application (Docker build output). Equivalent to `hop3 app logs --build`.

**Usage:**
```bash
hop3 app build-logs [--app <app>]
```

**Example:**
```bash
# Show build logs for myapp
hop3 app build-logs --app myapp
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

Restart an application. `hop3 restart` is a top-level alias.

**Usage:**
```bash
hop3 app restart [--app <app>]
```

**Example:**
```bash
hop3 app restart --app myapp
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
hop3 app start [--app <app>]
```

---

### `hop3 app stop`

Stop a running application.

**Usage:**
```bash
hop3 app stop [--app <app>]
```

**Notes:**
- Gracefully stops all processes
- Application remains configured (can be restarted)

---

### `hop3 app debug`

Show comprehensive debug information for an application.

**Usage:**
```bash
hop3 app debug [--app <app>]
```

**Notes:**
- Collects environment, logs, process status, and configuration
- Useful for troubleshooting deployment issues

---

### `hop3 app ping`

Check if an application is responding to HTTP requests.

**Usage:**
```bash
hop3 app ping [--app <app>] [path]
```

**Examples:**
```bash
hop3 app ping --app myapp          # root path
hop3 app ping --app myapp /health  # a specific endpoint
```

**Notes:**
- Performs HTTP health check on the application
- Returns response status and time

---

### `hop3 app destroy` ⚠️

**DESTRUCTIVE** - Destroy an app, removing all files and configuration. `hop3 destroy` is a top-level alias.

**Usage:**
```bash
hop3 app destroy [--app <app>]
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
hop3 app destroy --app myapp --yes
```

**⚠️ WARNING:** This operation is irreversible. Always backup before destroying.

---

## Environment Variables

The canonical command group is `env`. `config` is a back-compat alias, so every `hop3 env <sub>` below also works as `hop3 config <sub>`.

The target app is resolved from context when omitted; pass `--app <name>` to target a specific app explicitly.

### `hop3 env show`

Show all environment variables for an app.

**Usage:**
```bash
hop3 env show [--app <app>] [--sources]
```

Pass `--sources` to add a column showing where each variable comes from
(addon vs config) — this replaces the former `hop3 app env`.

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
- Use `env get` to retrieve specific values

---

### `hop3 env get`

Get a specific environment variable value.

**Usage:**
```bash
hop3 env get [--app <app>] <KEY>
```

**Example:**
```bash
hop3 env get --app myapp DATABASE_URL
# Output: postgresql://user:pass@localhost/db
```

---

### `hop3 env set`

Set environment variables for an app.

**Usage:**
```bash
hop3 env set [--app <app>] KEY1=value1 [KEY2=value2 ...]
```

**Arguments:**
- `--app <app>` - Target application (else resolved from context)
- `KEY=value` - One or more key-value pairs

**Examples:**
```bash
# Set single variable
hop3 env set --app myapp LOG_LEVEL=info

# Set multiple variables
hop3 env set --app myapp \
  DATABASE_URL=postgresql://localhost/db \
  REDIS_URL=redis://localhost:6379 \
  SECRET_KEY=mysecret

# Set variable with spaces (quote the value)
hop3 env set --app myapp MESSAGE="Hello World"
```

**Notes:**
- Requires app restart to take effect: `hop3 app restart --app myapp`
- Values are stored encrypted in database
- No leading/trailing whitespace in keys

---

### `hop3 env unset`

Unset (remove) environment variables for an app.

**Usage:**
```bash
hop3 env unset [--app <app>] KEY1 [KEY2 ...]
```

**Arguments:**
- `--app <app>` - Target application (else resolved from context)
- `KEY` - One or more keys to remove

**Examples:**
```bash
# Remove single variable
hop3 env unset --app myapp DEBUG

# Remove multiple variables
hop3 env unset --app myapp OLD_KEY DEPRECATED_VAR UNUSED_SECRET
```

---

### `hop3 env live`

Show live runtime environment of running app.

**Usage:**
```bash
hop3 env live [--app <app>] [--show-secrets]
```

**Options:**
- `--show-secrets` - Reveal full values instead of redacting secrets

**Notes:**
- Shows environment as currently loaded by running processes
- Useful for debugging configuration issues
- Fails loudly if the running environment can't be inspected (use `env show` for configured values)

---

### `hop3 app migrate`

Migrate configuration from another PaaS format to `hop3.toml`. The canonical command is `hop3 app migrate`; `hop3 env migrate` and `hop3 config migrate` are aliases. The source format and app directory are positional arguments.

**Usage:**
```bash
hop3 app migrate <from-format> <app-dir> [--dry-run] [--backup]
```

**Arguments:**
- `from-format` - Source format. Currently only `procfile` is supported.
- `app-dir` - Path to the application directory containing the source file.

**Options:**
- `--dry-run` - Preview the generated `hop3.toml` without writing it
- `--backup` - Back up the original file before writing (on by default)

**Example:**
```bash
# Preview the generated hop3.toml
hop3 app migrate procfile /path/to/app --dry-run

# Apply the migration
hop3 app migrate procfile /path/to/app
```

---

## Domain Management

Manage the hostnames bound to an app. These commands are a first-class view over the `HOST_NAME` env var that the reverse-proxy plugins (nginx / caddy / traefik) read. All write operations are atomic: every hostname is validated and conflicts with other apps are checked up front before anything is persisted. After every write you must redeploy (`hop3 deploy --app <app>`) for the proxy configuration to be updated.

For the declarative equivalent in `hop3.toml`, see [`[domains]`](./config.md#domains-application-hostnames).

### `hop3 domains list`

Show the hostnames currently bound to an app.

**Usage:**
```bash
hop3 domains list [--app <app>]
```

**Example:**
```bash
hop3 domains list --app abilian-cms
```

---

### `hop3 domains add`

Add one or more hostnames to an app (union, atomic, deduplicated).

**Usage:**
```bash
hop3 domains add [--app <app>] <host> [<host> ...]
```

**Example:**
```bash
hop3 domains add --app abilian-cms fermigier.com www.fermigier.com \
                                    abilian.com www.abilian.com
```

---

### `hop3 domains remove`

Remove one or more hostnames from an app. Errors if any of the requested hostnames is not currently bound.

**Usage:**
```bash
hop3 domains remove [--app <app>] <host> [<host> ...]
```

---

### `hop3 domains set`

Replace the full list of hostnames bound to an app.

**Usage:**
```bash
hop3 domains set [--app <app>] <host> [<host> ...]
```

**Example:**
```bash
hop3 domains set --app abilian-cms abilian.com www.abilian.com
```

---

### `hop3 domains clear`

Clear all hostnames from an app (unsets `HOST_NAME`).

**Usage:**
```bash
hop3 domains clear [--app <app>]
```

---

## Nix Commands

### `hop3 nix eject`

Materialize the auto-generated `hop3.nix` from a `[nix]` template config into a real `hop3.nix` file in the app's source directory. After ejection, the NixBuilder uses the committed `hop3.nix` instead of regenerating from the template, and the `[nix]` section in `hop3.toml` is ignored.

Use `nix eject` when you've outgrown the templates and need to customise the generated Nix expression directly.

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
hop3 backup create [--app <app>] [--no-addons]
```

**Options:**
- `--app <app>` - Application to backup (else resolved from context)
- `--no-addons` - Skip backing up attached addons (databases, etc.)

**Example:**
```bash
hop3 backup create --app myapp
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

Backup created: 20251112_143022_a8f3d9
Location: /home/hop3/.hop3/backups/apps/myapp/20251112_143022_a8f3d9/
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
│ 20251112_143022_a8f3d9      │ 45.2 MB  │ 2 hours ago   │ postgres │
│ 20251110_091534_b2c7e1      │ 43.1 MB  │ 2 days ago    │ postgres │
└─────────────────────────────┴──────────┴───────────────┴──────────┘
```

---

### `hop3 backup show`

Show detailed information about a backup. `hop3 backup info` is a back-compat alias.

**Usage:**
```bash
hop3 backup show <backup_id>
```

**Example Output:**
```
Backup Information

Backup ID: 20251112_143022_a8f3d9
Application: myapp
Created: 2025-11-12 14:30:22 UTC (2 hours ago)
Size: 45.2 MB

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
hop3 backup restore <backup_id> [--target-app NAME]
```

**Arguments:**
- `backup_id` - ID of backup to restore

**Options:**
- `--target-app` - Restore to a different app name (default: original app name)

**Examples:**
```bash
# Restore to original app (overwrites existing)
hop3 backup restore 20251112_143022_a8f3d9

# Restore to a new app name
hop3 backup restore 20251112_143022_a8f3d9 --target-app myapp-restored
```

**Process:**
1. Creates application if it doesn't exist
2. Restores source code
3. Restores data directory
4. Restores environment variables
5. Restores services (databases, etc.)
6. Verifies checksums

**Notes:**
- Does not automatically start the app (use `hop3 app restart --app <app>`)
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
WARNING: This will permanently delete the backup '20251112_143022_a8f3d9'.
Type 'DELETE' to confirm: DELETE
```

**Skip Confirmation:**
```bash
hop3 backup destroy 20251112_143022_a8f3d9 --yes
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
- `--primary` - Make this the primary addon of its type for the app (see below)

**Example:**
```bash
hop3 addon attach myapp-db --app myapp --service-type postgres
```

**Multiple addons of the same type:** the **first** addon of a type attached to
an app is the *primary* and injects the unprefixed connection vars
(`DATABASE_URL`, …). A **second** addon of the same type is *secondary* and its
vars are prefixed with `<ADDONNAME>_` (e.g. `REPLICA_DATABASE_URL`), so the two
never clobber each other. Use `--primary` to attach-and-promote (demoting the
current primary), or `hop3 addon promote` later.

**What Happens:**
- Service connection details added as environment variables (namespaced as above)
- Credentials stored encrypted in database
- App must be redeployed to use new variables

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
- Removes the addon's environment variables from the app (both the unprefixed
  and any prefixed spelling).
- Does not destroy the service itself; credentials removed from the app.
- If you detach the **primary** addon and same-type siblings remain, the oldest
  sibling is **auto-promoted** to primary (so the app keeps an unprefixed
  `DATABASE_URL`); this is reported in the output.

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

List provisioned addon instances (aliased to `hop3 addons`).

**Usage:**
```bash
hop3 addon list [--app <app>] [--type <type>]
```

**Options:**
- `--app` - Only addons attached to this application
- `--type` - Filter by addon type (postgres, mysql, redis)

**Example:**
```bash
# List all instances on the server
hop3 addon list

# List addons attached to an app
hop3 addon list --app my-app

# List PostgreSQL instances
hop3 addon list --type postgres
```

---

### `hop3 addon types`

List the addon types that can be provisioned with `hop3 addon create`.

**Usage:**
```bash
hop3 addon types
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

### `hop3 addon endpoint`

Show an addon's connection endpoint (URL, host, port). Type-agnostic: the addon's type is resolved from its name, so no `--type` is needed. This is what `hop3 tunnel` uses under the hood, but it's also handy on its own.

**Usage:**
```bash
hop3 addon endpoint <name>
```

**Notes:**
- Prints the connection URL plus host and port.
- Errors if the name is unknown, or ambiguous across two addon types.

---

### `hop3 addon exists`

Predicate for scripts/CI: exits **0** if the addon exists, **1** if it doesn't. Prints nothing in normal mode (use the exit code); with `--json` it also prints `{"exists": true|false}`. Type-agnostic; pass `--type` to require a specific type.

**Usage:**
```bash
hop3 addon exists <name> [--type <type>]
```

**Examples:**
```bash
hop3 addon exists mydb && hop3 addon promote mydb --app web
hop3 addon exists mydb --type postgres
hop3 addon exists mydb --json   # -> {"exists": true}
```

---

### `hop3 addon expose`

Make an addon reachable from outside the server on a stable, persisted host port, and print a connection URL. The addon normally listens only on `127.0.0.1`; `expose` allocates a public port, opens the firewall for it, and stands up a per-addon `systemd-socket-proxyd` forwarder to the addon's loopback port. The port survives server and addon restarts. Type-agnostic (the type is resolved from the name).

**Usage:**
```bash
hop3 addon expose <name> --source <cidr|any> [--host <fqdn>] [--type <type>]
```

**Options:**
- `--source <cidr|any>` - **Required.** Who may reach the port: a CIDR (e.g. `203.0.113.0/24`), or `any` to open it to the whole internet. Set `EXPOSE_DEFAULT_SOURCE` in `hop3-server.toml` to make a CIDR the per-server default; with no default and no flag, the command refuses (no accidental public database).
- `--host <fqdn>` - External hostname for the printed URL. Defaults to the server's canonical domain (`ADMIN_DOMAIN`); required if that isn't set.
- `--type <type>` - Disambiguate when one name exists across two addon types.

**Examples:**
```bash
hop3 addon expose mydb --source 203.0.113.0/24
# -> postgresql://user:pass@db.example.com:54312/mydb
hop3 addon expose mydb --source any --host db.example.com
```

**Notes:**
- The returned URL contains the addon password — treat it as a secret.
- `--source any` exposes the database to the entire internet; only the addon credentials protect it. Scope with a CIDR when you can.
- Idempotent: re-running returns the existing endpoint (no second port).
- `hop3 addon destroy` automatically unexposes first.

---

### `hop3 addon unexpose`

Remove an addon's public exposure: close the firewall port, remove the forwarder, and free the claim. Idempotent; the addon and its data are untouched.

**Usage:**
```bash
hop3 addon unexpose <name> [--type <type>]
```

---

### `hop3 addon promote`

Make an addon the **primary** one of its type for an app. When several same-type addons are attached, the primary injects the unprefixed connection vars (`DATABASE_URL`, …) and the others are prefixed (`<NAME>_DATABASE_URL`). This flips which one is primary; the previous primary becomes prefixed. Type-agnostic (type resolved from the name).

**Usage:**
```bash
hop3 addon promote <name> --app <app> [--type <type>]
```

**Example:**
```bash
hop3 addon promote replica-db --app myapp
# -> replica-db now owns DATABASE_URL; the old primary becomes <OLD>_DATABASE_URL
```

**Notes:**
- Idempotent: promoting the addon that is already primary is a no-op.
- Errors if the addon isn't attached to the app, or the type is ambiguous (pass `--type`).
- Redeploy the app for the env change to take effect.

---

### `hop3 addon <type> <verb>` — type-specific commands

Beyond the type-agnostic verbs above, each addon type exposes a few operations specific to it, under `hop3 addon <type> <verb> <name>`. The addon's type is part of the command path, so no `--type` flag is needed.

**Usage:**
```bash
# PostgreSQL
hop3 addon postgres credentials <name>          # Show connection env vars
hop3 addon postgres dump <name>                 # Back up via pg_dump
hop3 addon postgres restore <name> <path>       # Restore via psql ⚠️ overwrites
hop3 addon postgres extensions <name> <ext>...  # Install extensions (allow-listed)
hop3 addon postgres query <name> --command "SELECT 1"   # Ad-hoc SQL
hop3 addon postgres clone <source> <new-name>   # Copy data into a new addon
hop3 addon postgres export <name> > dump.sql    # Stream a dump to your machine
hop3 addon postgres import <name> --confirm=<name> < dump.sql   # Load a dump
hop3 addon postgres ps <name>                   # Active queries (diagnostics)
hop3 addon postgres locks <name>                # Current locks
hop3 addon postgres settings <name>             # Key configuration settings

# MySQL
hop3 addon mysql credentials <name>
hop3 addon mysql dump <name>                     # mysqldump
hop3 addon mysql restore <name> <path>           # ⚠️ overwrites
hop3 addon mysql query <name> --command "SELECT 1"
hop3 addon mysql clone <source> <new-name>       # Copy data into a new addon
hop3 addon mysql export <name> > dump.sql        # Stream a dump to your machine
hop3 addon mysql import <name> --confirm=<name> < dump.sql      # Load a dump
hop3 addon mysql ps <name>                       # Active queries (diagnostics)
hop3 addon mysql settings <name>                 # Key variables

# Redis
hop3 addon redis credentials <name>
hop3 addon redis dump <name>
hop3 addon redis restore <name> <path>           # ⚠️ overwrites
hop3 addon redis flush <name>                    # FLUSHDB ⚠️ deletes all keys
hop3 addon redis query <name> --command "DBSIZE" # Ad-hoc redis-cli command
hop3 addon redis clone <source> <new-name>       # Copy data into a new addon
hop3 addon redis export <name> > dump.rdb        # Stream a dump to your machine
hop3 addon redis import <name> --confirm=<name> < dump.rdb   # Load a dump
hop3 addon redis info <name>                     # Server INFO (diagnostics)

# S3
hop3 addon s3 credentials <name>
hop3 addon s3 dump <name>                         # Manifest (credentials + metadata)
hop3 addon s3 restore <name> <path>               # ⚠️ overwrites
hop3 addon s3 clone <source> <new-name>           # Copy data into a new addon
hop3 addon s3 export <name> > dump                # Stream a dump to your machine
hop3 addon s3 import <name> --confirm=<name> < dump   # Load a dump
```

**Available verbs by type:**

| Verb | postgres | mysql | redis | s3 |
|------|:---:|:---:|:---:|:---:|
| `credentials` | ✓ | ✓ | ✓ | ✓ |
| `dump` | ✓ | ✓ | ✓ | ✓ |
| `restore` | ✓ | ✓ | ✓ | ✓ |
| `extensions` | ✓ | | | |
| `flush` | | | ✓ | |
| `query` | ✓ | ✓ | ✓ | |
| `clone` | ✓ | ✓ | ✓ | ✓ |
| `export` / `import` | ✓ | ✓ | ✓ | ✓ |
| `ps` | ✓ | ✓ | | |
| `locks` | ✓ | | | |
| `settings` | ✓ | ✓ | | |
| `info` | | | ✓ | |

**Notes:**
- `credentials` prints the addon's connection variables (`DATABASE_URL`, `REDIS_URL`, `S3_*`, …) — treat the output as sensitive.
- `restore` and `redis flush` are destructive and prompt for confirmation (bypass with `-y` / `--confirm=<name>`).
- `dump` writes to the server's backup area and reports the path; redis/s3 `restore` are not available yet.
- `query` runs the statement as the addon's own (least-privilege) database user, confined to that addon's database. A SELECT renders as a table; other statements report the affected row count. The SQL/command is passed via `--command "…"`.
- `clone` creates a brand-new addon and loads a dump of the source into it (it refuses if the target already exists). Postgres/mysql only, since it builds on `restore`.
- `export` streams a dump to the client's **stdout** (redirect to a file); `import` reads a dump from the client's **stdin**. Because `import` overwrites data *and* stdin is the dump (so it can't prompt), pass `--confirm=<name>` or `--yes` with it. Postgres/mysql only.
- `ps` / `locks` / `settings` (postgres, mysql) and `redis info` are read-only diagnostics. The SQL ones run as the superuser so they see the whole database, and render as tables; `redis info` returns the server's INFO text.

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
┌───────────────────────────────────────────────────────────┐
│ Users                                                     │
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

The pre-0.5 commands `system check`, `system uptime`, and `system ps` were removed: `check` was renamed to `status` (it was always the rich health view), `uptime` is now part of the `status` and `info` identity header, and `ps` returned the entire host's process table over RPC and was removed as a security smell. For per-app process info, use `hop3 ps --app <app>`.

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

### `hop3 tunnel`

Open a local SSH tunnel to a remote addon and print a ready-to-paste local connection URL. This is a client-side command: it forwards a local port to the addon's port on the server over the configured SSH connection, then holds the tunnel open until you press Ctrl-C. The addon's type is resolved from its name (no `--type` needed). Requires an `ssh://` server.

**Usage:**
```bash
hop3 tunnel <addon-name> [--port <localport>]
```

**Options:**
- `--port <localport>` - Local port to bind (default: the addon's own port). Use this if the default port is already in use.

**Examples:**
```bash
hop3 tunnel mydb              # -> postgresql://...@127.0.0.1:5432/mydb
hop3 tunnel mydb --port 6543  # bind a different local port
hop3 tunnel mycache           # -> redis://...@127.0.0.1:6379/0
```

---

### `hop3 ps`

Show process count for an app.

**Usage:**
```bash
hop3 ps [--app <app>]
```

---

### `hop3 ps scale`

Set the process count for an app.

**Usage:**
```bash
hop3 ps scale [--app <app>] web=N [worker=M ...]
```

**Example:**
```bash
# Scale web processes to 3, worker processes to 2
hop3 ps scale --app myapp web=3 worker=2
```

---

### `hop3 app run`

Run a one-off command in the context of an app. `hop3 run` is a top-level alias. The app is read from the `--app`/`-a` flag (else resolved from context); everything that remains is the command line to execute.

**Usage:**
```bash
hop3 app run [--app <app>] <command> [args...] [--input <data>]
hop3 run [--app <app>] <command> [args...]   # top-level alias
```

**Options:**
- `--input <data>` - Data to send to the command's stdin (non-interactive)

**Examples:**
```bash
# Run database migrations (app from context)
hop3 app run python manage.py migrate

# Run a command for an explicit app
hop3 app run --app myapp python manage.py shell

# One-off script via the alias
hop3 run --app myapp node scripts/cleanup.js
```

---

### `hop3 app sbom`

Generate a Software Bill of Materials (SBOM) for an app.

**Usage:**
```bash
hop3 app sbom [--app <app>]
```

**Output:**
- CycloneDX format JSON
- Lists all dependencies with versions
- Security scanning metadata

---

## Exit Codes

The Hop3 CLI uses the exit-code table defined in ADR 036 D16. Scripts can distinguish user error from server error from "user said no" without parsing messages.

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

JSON output (`--json`) includes `error.exit_code` in the envelope so programmatic consumers don't have to mirror this mapping.

**Script tip.** Code `10` is your friend: use it to distinguish a user typing "no" at a confirmation prompt from an actual operation failure. Non-interactive scripts should pass `--confirm=<name>` or `--yes` to avoid it altogether, or `--no-input` to fail fast with an actionable message instead of hanging.

---

## Environment Variables

### Configuration

- **`HOP3_API_URL`** - Server URL (http://server or ssh://user@server)
- **`HOP3_API_TOKEN`** - API authentication token (overrides the token stored in the per-server credential store)
- **`HOP3_CONTEXT`** - Select a deploy environment / context (see [Context Management](#context-management))
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
2. **Protect your token** - The token lives in `~/.config/hop3-cli/credentials.toml` (created `0o600`, parent dir `0o700`); keep that file readable only by you
3. **Rotate tokens regularly** - Use `auth logout` and `auth login` to refresh
4. **Backup HOP3_SECRET_KEY** - Required to decrypt service credentials
5. **Use SSH connections** - Preferred over HTTP for remote servers

### Workflow

1. **Always backup before destructive operations:**
   ```bash
   hop3 backup create --app myapp
   hop3 app destroy --app myapp --yes
   ```

2. **Use `--dry-run` when available:**
   ```bash
   hop3 app migrate procfile . --dry-run  # Preview changes first
   ```

3. **Check status before and after operations:**
   ```bash
   hop3 app status --app myapp
   hop3 app restart --app myapp
   hop3 app status --app myapp  # Verify restart
   ```

4. **Use `--json` for automation:**
   ```bash
   apps=$(hop3 apps --json | jq -r '.apps[].name')
   for app in $apps; do
     hop3 backup create --app "$app"
   done
   ```

### Confirmation Prompts

Destructive commands require confirmation:
- **Type the resource name** - For `app destroy` and `addon destroy`, type the resource name
- **Type 'DELETE'** - For `backup destroy`
- **Skip with `-y`** - Use `--yes` flag to auto-confirm (use carefully!)

**Example:**
```bash
$ hop3 app destroy --app myapp
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

**Last Updated:** 2026-04-17
**CLI Version:** 0.5.0dev
**Server Version:** 0.5.0dev
