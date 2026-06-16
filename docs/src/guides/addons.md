# Addons

Addons are backing services — databases, caches, object storage — that your app depends on. Hop3 manages their lifecycle (create, attach, detach, destroy) and injects the connection details into your app as environment variables on deploy.

This guide covers the four addons shipped in Hop3 0.5: `postgres`, `mysql`, `redis`, and `s3`.

## Quick Start

The simplest way to use an addon is to declare it in `hop3.toml`. On first deploy, the addon is auto-provisioned; on subsequent deploys it's reused.

```toml
[metadata]
id = "my-django-app"

[run]
start = "gunicorn myapp.wsgi --bind 0.0.0.0:$PORT"

[[addons]]
type = "postgres"

[[addons]]
type = "redis"
```

After `hop3 deploy`, your app has `DATABASE_URL` and `REDIS_URL` in its environment — no further wiring needed.

## CLI Workflow

When you need imperative control (multi-app sharing, ad-hoc provisioning, destruction), use the `addon` commands.

### Create an addon

```bash
hop3 addon create postgres my-database
hop3 addon create redis my-cache
hop3 addon create mysql legacy-db
hop3 addon create s3 uploads
```

The addon name is free-form; pick one that describes the data, not the app. This keeps the name stable across apps that share the addon.

### Attach to an app

```bash
hop3 addon attach my-database --app my-app
hop3 addon attach my-cache --app my-app
```

Attach injects the addon's env vars into the app on the next deploy or restart. An addon can be attached to multiple apps (shared database pattern).

### Detach and destroy

```bash
hop3 addon detach my-database --app my-app     # Remove env vars; keep data
hop3 addon destroy my-database                 # Permanently delete (prompts)
```

`destroy` requires typed confirmation of the addon name. Pass `--confirm=<name>` to skip the interactive prompt in scripts. `--force` skips all safety checks.

### List and inspect

```bash
hop3 addon list                        # All provisioned instances (alias: addons)
hop3 addon list --app my-app           # Only addons attached to my-app
hop3 addon types                       # Addon types you can create
hop3 addon show my-database            # Full details for one addon
hop3 addon status my-database          # Health and connection check
```

### Type-specific commands

Each addon type adds a few operations under `hop3 addon <type> <verb> <name>` (the type is part of the command path, so no `--type` flag):

```bash
# Credentials (all types) — prints the connection env vars; treat as sensitive
hop3 addon postgres credentials my-database
hop3 addon redis credentials my-cache

# Dump / restore (postgres, mysql; redis/s3 dump only for now)
hop3 addon postgres dump my-database              # pg_dump → server backup dir
hop3 addon postgres restore my-database <path>    # psql restore (prompts)
hop3 addon mysql dump legacy-db
hop3 addon redis dump my-cache

# Postgres extensions (allow-listed)
hop3 addon postgres extensions my-database postgis pgvector

# Redis flush — empties the database, keeps the addon (prompts)
hop3 addon redis flush my-cache

# Ad-hoc query — runs as the addon's own (least-privilege) user
hop3 addon postgres query my-database --command "SELECT count(*) FROM users"
hop3 addon redis query my-cache --command "DBSIZE"
```

See the [CLI reference](../reference/cli.md#hop3-addon-type-verb-type-specific-commands) for the full per-type verb matrix.

## Addon Reference

### postgres

Provisions a PostgreSQL database owned by a per-app user with `CREATE ON DATABASE` + `CREATE, USAGE ON SCHEMA public` grants, so migrations can install trusted extensions (`pg_trgm`, `uuid-ossp`, `citext`) without superuser help.

**Injected env vars:**

| Variable | Example |
|----------|---------|
| `DATABASE_URL` | `postgres://myapp:pass@localhost:5432/myapp` |
| `PGDATABASE` | `myapp` |
| `PGUSER` | `myapp` |
| `PGPASSWORD` | (generated) |
| `PGHOST` | `localhost` |
| `PGPORT` | `5432` |

**Non-trusted extensions** (e.g. `postgis`, `pgvector`, `bloom`) cannot be installed by the per-app user. Declare them in `hop3.toml` and Hop3 will install them as superuser at provisioning time:

```toml
[[addons]]
type = "postgres"
extensions = ["postgis", "pgvector"]
```

Hop3 enforces an allow-list. The default set covers the PG13+ trusted extensions (`pg_trgm`, `hstore`, `citext`, `pgcrypto`, `uuid-ossp`, …) plus widely-used non-trusted ones audited to carry no privilege-escalation surface (`postgis`, `pgvector`, `bloom`, `cube`, `earthdistance`, `ip4r`, `pg_stat_statements`). To enable an additional extension on a specific Hop3 install — e.g. `pg_partman` or a vendor extension — set the operator-side env var `HOP3_EXTRA_PG_EXTENSIONS` (comma-separated). A small hard-deny set (`postgres_fdw`, `dblink`, `file_fdw`, `adminpack`, untrusted PL languages) cannot be enabled even via the override; those grant filesystem / network / arbitrary-code-execution capability and would defeat the separation between "deploy an app" and "execute as the postgres superuser".

> Some extensions (`pg_cron`, `timescaledb`) require `shared_preload_libraries` and a Postgres restart on top of `CREATE EXTENSION`. Hop3's default installer does not yet pre-load arbitrary extensions; treat those as a separate setup step.

### mysql

**Injected env vars:**

| Variable | Example |
|----------|---------|
| `DATABASE_URL` | `mysql://myapp:pass@localhost:3306/myapp` |
| `MYSQL_DATABASE` | `myapp` |
| `MYSQL_USER` | `myapp` |
| `MYSQL_PASSWORD` | (generated) |
| `MYSQL_HOST` | `localhost` |
| `MYSQL_PORT` | `3306` |

**Docker apps:** Hop3 grants MySQL access on multiple host patterns (`@'localhost'`, `@'127.0.0.1'`, `@'172.%'`) so apps reaching the host MySQL via the Docker bridge authenticate correctly. You don't need to think about this — it's automatic — but it's worth knowing if you inspect the `mysql.user` table.

### redis

A logical Redis database (numeric, 0–15 by default) is allocated per addon instance; multiple addons can coexist on the same Redis server.

**Injected env vars:**

| Variable | Example |
|----------|---------|
| `REDIS_URL` | `redis://127.0.0.1:6379/2` |
| `REDIS_HOST` | `127.0.0.1` |
| `REDIS_PORT` | `6379` |
| `REDIS_DB` | `2` |

Note: `REDIS_HOST` is `127.0.0.1` (not `localhost`) to avoid IPv6 resolution issues. For Docker apps, the Docker deployer rewrites `127.0.0.1 → host.docker.internal` at deploy time.

### s3

Provisions a bucket (named `hop3-<addon-name>`) and a scoped access key on the configured S3 backend (MinIO in 0.5; Garage planned for 0.6).

**Injected env vars:**

| Variable | Example |
|----------|---------|
| `S3_ENDPOINT` | `http://localhost:9000` |
| `S3_BUCKET` | `hop3-uploads` |
| `S3_ACCESS_KEY` | (generated) |
| `S3_SECRET_KEY` | (generated) |
| `S3_REGION` | `us-east-1` |
| `S3_USE_PATH_STYLE` | `true` |

Path-style URLs are required for MinIO; virtual-host style will arrive with the Garage backend.

## Common Patterns

### Mapping to app-specific variable names

If your app expects variables like `DB_HOST` or `CACHE_URL` rather than the canonical Hop3 names, remap in `[env]`:

```toml
[env]
DB_HOST = "${PGHOST}"
DB_PORT = "${PGPORT}"
DB_NAME = "${PGDATABASE}"
DB_USER = "${PGUSER}"
DB_PASS = "${PGPASSWORD}"
CACHE_URL = "${REDIS_URL}"
```

Or — for apps that translate only at runtime (e.g. Django reading `POSTGRES_USER`) — wrap the start command:

```toml
[run]
start = "env POSTGRES_USER=$PGUSER POSTGRES_PASSWORD=$PGPASSWORD POSTGRES_DB=$PGDATABASE POSTGRES_HOST=$PGHOST POSTGRES_PORT=$PGPORT gunicorn myapp.wsgi:application --bind 0.0.0.0:$PORT"
```

### Sharing an addon across apps

```bash
hop3 addon create postgres shared-db
hop3 addon attach shared-db --app api
hop3 addon attach shared-db --app worker
hop3 addon attach shared-db --app admin
```

Each app receives the same `DATABASE_URL` and can coordinate via the shared database.

### Multiple addons of the same type

Declare one `[[addons]]` block per instance:

```toml
[[addons]]
type = "redis"
name = "session-store"

[[addons]]
type = "redis"
name = "job-queue"
```

Env-var prefixing for distinct instances is planned for 0.6; in 0.5, only the first attached instance's variables (`REDIS_URL`, etc.) are injected.

## Backup and Restore

Addons are included in app-level backups by default. See [Backup & Restore](backup-restore.md).

```bash
hop3 backup create --app my-app           # Includes attached addon data
hop3 backup create --app my-app --no-addons   # App code + env only
```

For a single addon, `hop3 addon <type> dump <name>` writes a standalone dump to the server's backup area, and `hop3 addon <type> restore <name> <path>` restores it (postgres and mysql; redis/s3 restore is planned).

## See Also

- [hop3.toml reference: `[[addons]]`](../reference/config.md) — full schema
- [Backup & Restore](backup-restore.md)
- [Troubleshooting](troubleshooting.md)
