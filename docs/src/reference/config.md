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

### `[metadata]` - Application Metadata

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

### `[build]` - Build Configuration

Controls how your application is built and prepared for deployment.

```toml
[build]
# Builder to use: "auto", "local", "docker", or "nix"
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
  - `"nix"`: Build with Nix (hand-crafted `hop3.nix` or a generated `[nix]` template — see [`[nix]`](#nix-template-based-nix-builds))
- `toolchain` (string): Force a specific language toolchain (`python`, `node`, `ruby`, `go`, `rust`, `static`, …), overriding auto-detection. Rarely needed — toolchains are normally detected from project files.
- `build` (string | array): Main build commands
- `before-build` (string | array): Pre-build commands (maps to Procfile `prebuild`)
- `test` (string | array): Test commands to run after build
- `packages` (array): System packages required for building
- `pip-install` (array): Python packages to install during build
- `ignore` (array): Gitignore-style patterns excluded from the `hop3 deploy` upload (see below)
- `static-dir` (string): For a static site (`toolchain = "static"`), the directory to serve, relative to the app root (e.g. `"site"`, `"html"`, `"dist"`). Defaults to `"public"`. See [Static sites](#static-sites) below.

**Procfile Mapping:**
- `build.before-build` → Procfile `prebuild`

#### `ignore` - Excluding files from the upload

When you run `hop3 deploy`, the CLI tars your working tree and uploads it. `[build].ignore` is the single, canonical way to say what *not* to upload:

```toml
[build]
ignore = ["*.log", "tmp/", "coverage/", "*.sqlite3"]
```

Patterns use gitignore syntax (including `!` negation), and are added **on top of** Hop3's built-in defaults — VCS metadata and dependency/build/cache dirs that the server regenerates (`.git/`, `node_modules/`, `target/`, `.venv/`, `venv/`, `__pycache__/`, `*.py[cod]`, `.idea/`, `.DS_Store`, `.mypy_cache/`, `.pytest_cache/`, `.ruff_cache/`, `*.egg-info/`). So most apps need no `ignore` at all. (`target/` is Rust/Maven build output — the server rebuilds it from source.)

**Other ignore files are scoped to their own deployment method — they do *not* affect the `hop3 deploy` upload:**

- **`.gitignore`** applies to the **git-push** deploy path (git itself decides what reaches the server). It is not consulted for the `hop3 deploy` upload.
- **`.dockerignore`** applies to the server-side **`docker build`** context when `builder = "docker"` (Docker honors it there). It is not applied to the upload.

> The legacy `.hop3ignore` sidecar and the `[build].ignore-file` pointer are removed. Move any `.hop3ignore` patterns into `[build].ignore`; a leftover `.hop3ignore` is still read for one transition release with a deprecation warning, and `[build].ignore-file` is now a hop3.toml validation error.

#### Static sites

A static site (`toolchain = "static"`) is served straight from disk by nginx — no app process, and **no Procfile required**. Point Hop3 at the directory of files with `static-dir`:

```toml
[build]
toolchain = "static"
static-dir = "site"     # "html", "dist", … — defaults to "public"
```

The served directory is resolved in this order (first match wins):

1. `[build].static-dir` — the canonical, first-class key.
2. `[run.workers].static` — the equivalent worker spelling (back-compat).
3. A Procfile `static: <dir>` line.
4. `public` — the default when nothing is declared.

So `[build].static-dir` (or just relying on the `public` default) is all a static site needs; the worker and Procfile forms exist only for compatibility.

### `[run]` - Runtime Configuration

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

### `[env]` - Environment Variables

Define environment variables for your application.

```toml
[env]
DATABASE_URL = "postgresql://localhost/mydb"
SECRET_KEY = "your-secret-key"
ALLOWED_HOSTS = "myapp.example.com"
LOG_LEVEL = "info"
```

**Notes:**

- Sensitive values should be injected through `hop3 config set`, not hardcoded in hop3.toml. For secrets the app needs to *exist* before its first boot, use a generated secret (below) instead of a manual `config set`.
- The `DEBUG` environment variable defaults to `false`. Only set `DEBUG = "true"` in development environments for troubleshooting—never in production.

#### Generated secrets

Some apps require a secret or key to exist *before they boot* (e.g. Phoenix `SECRET_KEY_BASE`, Laravel `APP_KEY`, Rails `secret_key_base`) — the release crashes without it, so there is no chance to set it afterwards. Declare such a value as a generated secret and Hop3 creates it for you on first deploy:

```toml
[env]
SECRET_KEY_BASE = { generate = "hex", length = 64 }
APP_KEY         = { generate = "base64", length = 32, prefix = "base64:" }
ADMIN_PASSWORD  = { generate = "password", length = 24, display = true }
SESSION_ID      = { generate = "uuid" }
```

**Fields:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `generate` | string | yes | `hex`, `base64`, `urlsafe`, `password`, or `uuid` |
| `length` | integer | no | Entropy: bytes for `hex`/`base64`/`urlsafe`, characters for `password`; ignored for `uuid`. Per-generator default when omitted (32 bytes / 24 chars) |
| `prefix` | string | no | Literal string prepended to the value (e.g. `base64:` for Laravel) |
| `display` | boolean | no | If `true`, the generated value is shown **once** in the deploy output, for bootstrap credentials. Default `false` |

**Semantics:**

- The value is generated with a cryptographically secure RNG only when the variable is currently **unset**, then stored as a normal app env var (visible in `hop3 config show`).
- It is **generated once and never rotated** on redeploy — so redeploys stay idempotent and a regenerated secret never silently invalidates existing sessions or data. Setting `_policy = "override"` does *not* force rotation.
- To rotate a generated secret, run `hop3 config unset --app <app> KEY` and redeploy.
- A malformed spec (unknown generator, `length < 1`, unknown field) is a hop3.toml validation error — it fails the deploy loudly rather than producing a bad secret.

#### Dynamic references

Most apps need nothing here: attaching an addon already injects its standard variables (`DATABASE_URL`, `PGHOST`, `REDIS_URL`, …), and `[env.computed]` assembles custom strings from them. A reference is for the cases those can't express — copying one specific attribute, or reading an app fact:

```toml
[env]
# Copy one attribute from a declared addon's credentials. `key` is one of the
# addon's injected variable names (run `hop3 config show` to see them).
PRIMARY_DB_HOST = { from = "myapp-db", key = "PGHOST" }

# App facts (no `from`): "domain"/"hostname" → the app's first hostname,
# "name" → the app name.
APP_FQDN = { key = "domain" }
```

**Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `from` | string | Name of an addon attached to this app. Omit for app facts. |
| `key` | string | The attribute to copy: an addon variable name (with `from`), or an app fact (`domain`, `hostname`, `name`). |
| `external_ip` | boolean | The host's public IP. **Not implemented yet** — declaring it fails the deploy with a clear message; use `hop3 config set` meanwhile. |

**Semantics:**

- References are **derived** values resolved fresh on every deploy (like `[env.computed]`), so they overwrite. Resolution order is: addon auto-injection → static `[env]` → generated secrets → **references** → `[env.computed]`. A `{ key = "domain" }` ref therefore sees the hostname from `[domains]`, and a `[env.computed]` template can interpolate a resolved reference.
- Resolution **fails the deploy loudly** if the addon isn't attached, the key doesn't exist (the error lists the available keys), or the app fact is unknown — never a wrong or empty value.
- `{ from = ..., key = ... }` resolves against this app's own addons only; it can't read another app's credentials.

### `[domains]` - Application Hostnames

Declare the hostnames the reverse proxy should bind to your app.

```toml
[domains]
list = ["abilian.com", "www.abilian.com", "fermigier.com", "www.fermigier.com"]
_policy = "keep-existing"   # optional; "override" to overwrite on every deploy
```

**Fields:**

- `list` (array of strings, required when section is present): hostnames bound to this app, in declaration order. Each entry must be a valid RFC-1123 hostname. The special value `"_"` is the nginx catch-all and may only appear alone.
- `_policy` (string, optional, default `"keep-existing"`): merge policy. Mirrors `[env]._policy`. With `"keep-existing"`, a manually set HOST_NAME (via `hop3 config set` or `hop3 domains`) is preserved across deploys. With `"override"`, the value from `hop3.toml` is reapplied on every deploy.

**Notes:**

- `[domains].list` is mutually exclusive with `HOST_NAME` under `[env]`. Setting both is a hop3.toml validation error — use one or the other.
- At deploy time, the section is translated into the `HOST_NAME` env var that the reverse-proxy plugins (nginx / caddy / traefik) read.
- An empty list (`list = []`) is a no-op: HOST_NAME is **not** unset. Use `hop3 domains clear --app <app>` to remove the binding explicitly.
- For CRUD from the CLI, see `hop3 domains` in the CLI reference.

### `[contexts.<name>]` - Deploy Environments

A **context** is a named target, and `--context <name>` is the one CLI selector for every command. A context exists at two scopes, and `[contexts.<name>]` appears in **two files**:

- In the **committed `hop3.toml`** (documented here): a full deploy environment — `dev`, `staging`, `prod` — each a distinct app instance, usually on a different server, with its own domains and non-secret configuration. One codebase, many environments.
- In the per-developer **`config.toml`**: a *global* context, the same block pared to just `server = "<addr>"` — a name bound to a server address, so project-less commands (`hop3 apps --context prod`) can target a server by name. Server-only, no `app`/`domains`/`env`.

`--context <name>` resolves **project-first, then global**. Neither file holds a secret: the `server` is always a literal address, and the bearer token lives only in the credential store (see below). See [ADR 042](https://github.com/abilian/hop3/blob/main/notes/adrs/042-cli-context-model.md) for the full model.

```toml
[metadata]
id = "myapp"

[contexts.prod]
server = "ssh://root@prod.example.com"   # literal address of the target server
app    = "myapp"                          # app instance for this environment
[contexts.prod.domains]
list = ["myapp.com", "www.myapp.com"]
[contexts.prod.env]
LOG_LEVEL = "warning"

[contexts.dev]
server = "ssh://root@dev.example.com"
app    = "myapp-dev"
[contexts.dev.domains]
list = ["myapp.dev.example.com"]
[contexts.dev.env]
LOG_LEVEL = "debug"
```

Deploy a specific environment with `hop3 deploy --context prod`. (When `hop3.toml` declares exactly one context, it is selected automatically.)

**Fields:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `server` | string | yes | **Literal address** of the target Hop3 instance, e.g. `ssh://root@prod.example.com`. Never a symbolic name, and never a credential — the bearer token lives in the local credential store (see below). An address that embeds credentials (`scheme://user:password@…`, or a `token=`/`password=` query param) is a hop3.toml validation error. |
| `app` | string | no | App instance name for this environment. Inherits `[metadata].id` when omitted. |
| `[contexts.<name>.domains]` | table | no | Hostnames for this environment — **same shape as the top-level [`[domains]`](#domains-application-hostnames)** (a `list = [...]` table, with the same RFC-1123 / catch-all rules). When present, the context's domains **replace** the top-level `[domains]` on deploy; when absent, the top-level domains are inherited unchanged. |
| `[contexts.<name>.env]` | table | no | Per-environment **non-secret** env overrides. These **merge over** the top-level `[env]`, key by key, on deploy. |

**Notes:**

- **Context names** must match `^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$` — start with a letter or digit, then letters / digits / `-` / `_`, up to 64 characters. (They appear unquoted on the CLI and as TOML keys, so they are kept shell-friendly.)
- **Resolution and flattening happen client-side, on deploy.** The CLI selects the context (via `--context`, `$HOP3_CONTEXT`, `.hop3-local.toml`, or the single-context fallback), computes the effective config — the context's `app`, its `domains` (replacing the top-level) and `env` (merged over the top-level) — and applies it. Every `[contexts.*]` block is then **stripped from the uploaded file**, so what the server validates and deploys is the flattened result (preview == deploy). The deployer never interprets `[contexts.*]`.
- **No secrets here** — see the zero-secrets rule below. A context's `[env]` is scanned by the same committed-credential tripwire as the top-level `[env]`; per-environment secrets are set server-side per app with `hop3 env set`.
- Within a single context, declaring both `domains` and a `HOST_NAME` in that context's `[env]` is a validation error — use one or the other (mirroring the top-level rule).
- These blocks can be hand-written or managed with `hop3 context add` / `remove` / `rename`; `hop3 context use <name>` selects an environment for the current checkout. See the [CLI reference](cli.md) for the verbs.

### Zero secrets in `hop3.toml`

`hop3.toml` is **committed and shared, and must hold no secrets.** This is not only convention: the schema **rejects** committed `[env]` (and `[contexts.*.env]`) values that look like a secret — a **committed-credential tripwire** that fails validation loudly rather than letting an obvious credential slip into version control. It flags known API-key shapes (`sk_live_…`, `sk_test_…`, `ghp_…`, `github_pat_…`, `xoxb-…`, `AKIA…`, …) and connection strings with embedded credentials (`scheme://user:password@…`). It is best-effort, not a proof — a novel secret shape could still slip through — so treat it as a backstop, not a license to put secrets in the file.

Secrets are never put in `hop3.toml`. They live **server-side, per app instance**, in three forms:

1. **Autogenerated keys** (e.g. `FLASK_SECRET_KEY`, `SECRET_KEY_BASE`, session keys) — provisioned automatically on first deploy with a CSPRNG and stored as encrypted env vars (generated-once). Declare these as [generated secrets](#generated-secrets) — the spec, not the value, lives in `hop3.toml`.
2. **Addon credentials** (`DATABASE_URL`, `REDIS_URL`, …) — managed entirely by the platform: provisioned, encrypted, and injected automatically when you attach an addon. You never write them down.
3. **Third-party secrets** (Stripe, Sentry, OAuth client secrets, …) — set manually, per app, with `hop3 env set` (which stores them as encrypted `EnvVar`s). Because each context deploys a distinct app instance, these are already scoped per environment.

Because each context targets a distinct app instance (`myapp` vs `myapp-dev`), per-environment secrets are already isolated by per-app server-side storage — no secret machinery in the repo.

### Where bearer tokens live (not in `hop3.toml`)

The bearer token used to *talk to* a server is **not** in `hop3.toml` (it is shared) — nor in `config.toml`. It lives in the per-server **credential store** at `~/.config/hop3-cli/credentials.toml` (file mode `0o600`, keyed by canonical server address), written by `hop3 login` / `hop3 init`. A context's `server` field names the address; the CLI looks up that address's token in the credential store at deploy time. The credential store is documented more fully in the [CLI reference](cli.md).

### `[port]` - Port Configuration

Specify ports for different services.

```toml
[port]
web = 8000
api = 8080
metrics = 9090
```

### `[[ports]]` - Fixed Host Ports (non-HTTP)

For HTTP/HTTPS apps you don't declare ports at all — Hop3 assigns a dynamic `$PORT` and the reverse proxy routes by hostname, so any number of apps share `:80`/`:443`. But non-HTTP services (SMTP, XMPP, RTMP, Matrix federation, …) have no proxy and no virtual hosting: the app binds a fixed host port directly, so **exactly one app can own a given port** on the server.

Declare those ports with `[[ports]]`. Hop3 records each in a host-wide registry, **refuses a second app that declares the same port — before it builds — with a clear error**, opens the firewall for it on a successful deploy, and closes it on teardown.

```toml
[[ports]]
number = 1935
protocol = "tcp"
name = "rtmp"        # optional label, for diagnostics

[[ports]]
number = 8448
protocol = "tcp"
name = "federation"

[[ports]]
number = 5432
protocol = "tcp"
name = "postgres"
source = "10.0.0.0/8"   # restrict to a private network instead of the whole internet
```

**Fields:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `number` | integer | yes | Port number, 1–65535 |
| `protocol` | string | no | `tcp` (default) or `udp` |
| `name` | string | no | Human-readable label, for diagnostics only |
| `source` | string | no | `any` (default, whole internet) or an IPv4 CIDR to restrict who may reach the port |

**Notes:**

- Don't list your HTTP port here — that one is dynamic (`$PORT`) and proxied. `[[ports]]` is only for ports the app binds directly to the host.
- Two apps declaring the same `(number, protocol)` cannot coexist (there is no proxy to multiplex them). The second deploy is rejected up front with a message naming the app that already holds the port.
- Ports `22`, `80`, and `443` are reserved by Hop3 (SSH and the reverse proxy) and rejected — HTTP apps use `$PORT` and are proxied.
- By default a declared port is opened to the **whole internet** (`source = "any"`). Set `source` to an IPv4 CIDR (e.g. `"10.0.0.0/8"`) to restrict it to a network — useful for an addon or admin port that should only be reachable over a VPN or private link. IPv6 source CIDRs aren't supported yet.
- See what is currently claimed and whether the firewall is actually open with `hop3 ports`.
- **Native/Nix builds only.** A Docker-deployed app's container does not yet publish declared ports to the host, so for Docker apps the port is *claimed* (conflict-checked) but the firewall is not opened. Use a native or Nix build for an app that needs a fixed host port.
- Opening the firewall needs the `hop3-rootd` daemon. If it isn't running the port is still *claimed* (so the conflict check works), but it won't be reachable externally until rootd applies the rule.

### `[[volumes]]` - Persistent Volumes

Each deploy replaces your app's source tree (`src/` is wiped and re-extracted), so anything written *inside* it is lost on the next deploy. A `[[volumes]]` declares a directory that must **survive** redeploys:

```toml
[[volumes]]
name = "uploads"
target = "data/uploads"
```

Hop3 stores the data under the app's data root (`<app>/volumes/<name>/`) — outside `src/` — and links `target` to it on every deploy, so writes persist. On the first deploy, if your source ships content at `target`, it seeds the (empty) volume once; afterwards the volume is the source of truth.

**Fields:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | yes | Logical name; storage lives at `<app>/volumes/<name>/`. Letters, digits, `-`, `_` |
| `target` | string | yes | Directory inside the app tree to persist. Relative, no `..` |
| `type` | string | no | `persist` (default). `tmpfs` / `bind` are recognized but **not implemented yet** (they fail the deploy with a clear message) |
| `size` | string | no | Size cap for a future `tmpfs` volume (e.g. `"256M"`) |
| `mode` | string | no | Octal permissions for the volume directory |

**Notes:**

- `target` must be a **directory** path relative to the app's source tree; absolute paths and `..` are rejected. A file already at `target` is an error — volume targets are directories.
- Persist volumes need no `hop3-rootd`: the link lives under the app's own directories. `tmpfs`/`bind` will need privileged mounts and are deferred.
- Volumes are included in `hop3 backup create` by default; set `[volumes.backup]` `include = false` to opt a volume out.

### `[limits]` - Resource Caps

Cap an app's resource use so one app can't starve others on the same server:

```toml
[limits]
memory = "512M"     # hard memory cap
cpu = 1.5           # CPU cores (fractional allowed)
processes = 256     # max processes/threads
```

**Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `memory` | string | Memory cap: a number with an optional `K`/`M`/`G` suffix (e.g. `512M`, `1G`), or plain bytes |
| `cpu` | number | CPU cores, fractional allowed (e.g. `1.5`) |
| `processes` | integer | Maximum processes/threads |

**Notes:**

- A declared limit is a **safety guarantee**: if it can't be enforced, the deploy fails loudly rather than running an app that only *looks* capped.
- Enforcement is implemented for the **Docker builder** (compose `mem_limit` / `cpus` / `pids_limit`). Native/Nix enforcement needs cgroups via `hop3-rootd` and isn't available yet, so declaring `[limits]` on a non-Docker app **aborts the deploy** with a clear message until then.

### `[healthcheck]` - Health Check Configuration

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
- `retries` (number): Number of failed checks before the app is marked unhealthy

### `[backup]` - Backup Configuration

Backups are created **on demand** with `hop3 backup create --app <app>` and restored with `hop3 backup restore <id>` (where `<id>` is the backup id, not the app). A backup captures the app's source, environment variables, attached addons (e.g. a Postgres dump), the app's `data/` directory, **and every `[[volumes]]` volume** (each archived as its own unit) — so persistent data round-trips through restore.

```toml
[backup]
paths = ["var/state", "uploads"]   # extra app dirs to also archive
exclude = ["*.tmp", "cache/*", "node_modules"]  # patterns to prune
```

**Fields:**
- `exclude` (array): glob patterns pruned from the source and `data/` archives. A pattern matches the full path relative to the archived root (`cache/*`), a basename (`*.tmp`), or any single path segment (`node_modules`). Use it to keep regenerable or bulky files out of backups.
- `paths` (array): **additional** app-relative directories to archive (into `extra.tar.gz`), beyond the whole source tree captured by default. Resolved relative to the app's source dir and **confined to the app tree** — an entry that escapes it (absolute path or `..`) fails the backup loudly. A declared directory that doesn't exist yet is skipped. Restored back into place on `hop3 backup restore`.

**Notes:**
- A `[[volumes]]` volume can opt out of backup with `[volumes.backup]` `include = false`.
- Automated scheduling and retention are not implemented yet; run `hop3 backup create` from a cron job if you need a schedule.

### `[[addons]]` - Backing Services

Declare backing services your application needs (databases, caches, object storage). Each `[[addons]]` entry auto-provisions the addon on first deploy if it doesn't already exist, and injects connection env vars into the app runtime.

```toml
[[addons]]
type = "postgres"

[[addons]]
type = "redis"

[[addons]]
type = "mysql"

[[addons]]
type = "s3"
```

**Note:** Use `[[addons]]` (double brackets) for arrays in TOML. The legacy `[[provider]]` section name is deprecated; prefer `[[addons]]`.

**Common fields:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | string | yes | Addon type: `postgres`, `mysql`, `redis`, `s3` |
| `name` | string | no | Instance name; defaults to the app name. Multiple addons of the same type on one app should set distinct names |

**Addon-specific fields:**

`postgres`:

| Field | Type | Description |
|-------|------|-------------|
| `extensions` | `list[string]` | Non-trusted PostgreSQL extensions to install as superuser (e.g. `["postgis", "pgvector", "bloom"]`). Trusted extensions (`pg_trgm`, `uuid-ossp`, etc.) can be installed by the per-app user via migrations and do not need to be listed here. The platform enforces an allow-list — see `docs/src/guides/addons.md` for the default set, the operator override (`HOP3_EXTRA_PG_EXTENSIONS`), and the hard-deny set. |

Example:

```toml
[[addons]]
type = "postgres"
extensions = ["postgis", "pgvector"]
```

**Injected environment variables (per addon type):**

| Type | Variables |
|------|-----------|
| `postgres` | `DATABASE_URL`, `PGDATABASE`, `PGUSER`, `PGPASSWORD`, `PGHOST`, `PGPORT` |
| `mysql` | `DATABASE_URL`, `MYSQL_DATABASE`, `MYSQL_USER`, `MYSQL_PASSWORD`, `MYSQL_HOST`, `MYSQL_PORT` |
| `redis` | `REDIS_URL`, `REDIS_HOST`, `REDIS_PORT`, `REDIS_DB` |
| `s3` | `S3_ENDPOINT`, `S3_BUCKET`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_REGION`, `S3_USE_PATH_STYLE` |

For CLI-level addon management (`addon create`, `addon attach`, `addon detach`, `addon destroy`) and end-to-end examples, see [Addons Guide](../guides/addons.md).

### `[test]` - Test Harness Metadata

Optional section for the `hop3-test` framework. Holds fields that are genuinely test-specific; everything else (app name, description, addons, healthcheck path) is derived from the rest of `hop3.toml`. Replaces the separate `test.toml` file (removed 2026-04-21 — one source of truth per app).

```toml
[test]
priority = "P1"                        # P0 | P1 | P2
tier = "medium"                        # fast | medium | slow | very-slow (display label only)
targets = ["docker", "remote"]         # which hop3-test targets can run this app
author = "hop3-team"
covers = ["python", "flask", "postgres"]

[[test.validations]]                   # Additional HTTP probes beyond [healthcheck]
path = "/api/health"
status = 200
contains = "ok"

[[test.validations]]
path = "/"
status = 200
```

**Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `priority` | string | `P0`, `P1`, or `P2`. Determines which test profile (`dev`, `ci`, `release`) runs this app |
| `tier` | string | `fast`, `medium`, `slow`, or `very-slow`. **Report label only** — no longer drives any timeout (all builds + deploys share a single 30-minute budget). |
| `targets` | array | Which `hop3-test` targets support this app: `"docker"`, `"remote"` |
| `author` | string | Optional documentation |
| `covers` | array | Free-form tags for what the test exercises |
| `[[test.validations]]` | table array | HTTP probes run after deploy. Each takes `path`, `status`, optionally `contains` |

**Notes:**

- The `[test]` section is entirely optional. When absent, `hop3-test` uses sensible defaults (priority P1, single healthcheck-path HTTP probe at status 200).
- **Derived automatically** from the rest of `hop3.toml` — do not duplicate in `[test]`:
  - Test name: from `[metadata].id` or directory path.
  - Category: from `[build].builder` (`"nix"` → `nix-app`, `"docker"` → `docker-app`, `"local"` → `deployment`).
  - Required services: from `[[addons]]` plus implicit `nix` / `docker` based on builder.
  - Base healthcheck path: from `[healthcheck].path`.

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

[[addons]]
type = "postgres"
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

[[addons]]
type = "postgres"
```

## `[nix]` — Template-Based Nix Builds

When `builder = "nix"` is set in `[build]`, Hop3 can generate a Nix expression automatically from a `[nix]` section instead of requiring a hand-crafted `hop3.nix` file. This removes the Nix learning curve for most deployments.

### How It Works

1. If a `hop3.nix` file exists in the source directory, it is used directly (hand-crafted mode).
2. If no `hop3.nix` exists but `[nix].template` is set, Hop3 generates one at build time from the template.
3. Run `hop3 nix eject <app>` to materialize the generated file for manual customization.

### Template Types

Nine templates are available. Prefer the higher tiers when possible — see [Nix reference](nix.md#reproducibility-tiers) for the reproducibility implications.

| Template | Use case | Tier |
|----------|----------|------|
| `nixpkgs-wrapper` | Apps already packaged in nixpkgs (best — multi-arch, source-built) | 1 |
| `python-venv` | Python apps installed via pip into a virtualenv | 2 |
| `php-app` | PHP apps served with `php -S` or `artisan serve` | 2 |
| `java-war` | Java WAR files served with a JDK from nixpkgs | 1 |
| `ruby-bundler` | Ruby apps using `bundlerEnv` from `gemset.nix` | 2 |
| `node-pnpm-install` | Node.js apps installed from npm via `pnpm install` | 2 |
| `prebuilt-binary` | Pre-compiled single binary from upstream releases | 3 |
| `prebuilt-archive` | Pre-compiled archive with multiple files | 3 |
| `node-prebuilt` | Node.js apps with pre-built assets | 3 |

**Tier 1 = source-built and reproducible** (use when available). **Tier 2 = source-built but not fully hermetic** (depends on PyPI, Packagist, etc. at build time). **Tier 3 = pre-built binary download** (x86_64-linux only, not reproducible from source — use only when nothing in nixpkgs fits).

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

This is the recommended pattern: wrap a nixpkgs source build with a startup script that generates the app.ini config from environment variables.

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
hop3 app migrate procfile /path/to/app --dry-run
```

This will generate a hop3.toml from your Procfile. Review and customize as needed.

## See Also

- [Procfile Reference](https://devcenter.heroku.com/articles/procfile)
- [Migration Guide](../guides/migration-guide.md)
- Examples
