# Lessons Learned: Database Addon Portability

Pitfalls when providing database services (PostgreSQL, MySQL, Redis) to applications across different platforms and runtimes.

## localhost vs 127.0.0.1

Never use `localhost` as the default database host. On IPv6-enabled servers, runtimes resolve `localhost` to `::1` first. If the database only listens on `127.0.0.1`, the connection fails with `ECONNREFUSED ::1:3306`.

Node.js is the most common offender — its DNS resolver prefers IPv6. Python and Go typically try both.

**Fix:** Always inject `127.0.0.1` as the host value. For Docker deployments, the Docker deployer transforms `127.0.0.1` → `host.docker.internal` automatically.

## MySQL User Host Matching

MariaDB's user matching has a non-obvious priority: `''@'localhost'` (anonymous user, specific host) beats `'myuser'@'%'` (named user, any host) for connections from localhost.

If the anonymous user exists (common in default installations), creating app users with `@'%'` means they can never connect from localhost — the anonymous user matches first and authentication fails.

**Fix:** Create users with `@'localhost'` for local-only services:

```sql
CREATE USER 'myuser'@'localhost' IDENTIFIED BY 'pass';
GRANT ALL ON mydb.* TO 'myuser'@'localhost';
```

## MySQL Per-Host Grants for Docker-Bridge Apps

A single `@'localhost'` grant is not enough when Docker-based applications on the same host talk to MySQL. Docker containers connect from the bridge network (typically `172.16.0.0/12` — usually `172.17.x.x` or `172.18.x.x`), not from `localhost`. The connection attempt surfaces as:

```
Host '172.18.0.2' is not allowed to connect to this MariaDB server
```

The MySQL protocol doesn't fall back between grant hosts — the server picks the most-specific matching user row at authentication and rejects if the password doesn't match *that* row. So one user row per connection source is required.

**Fix:** Create three user rows per app, with identical privileges:

```sql
CREATE USER 'myuser'@'localhost'   IDENTIFIED BY 'pass';
CREATE USER 'myuser'@'127.0.0.1'   IDENTIFIED BY 'pass';
CREATE USER 'myuser'@'172.%'       IDENTIFIED BY 'pass';
GRANT ALL ON mydb.* TO 'myuser'@'localhost';
GRANT ALL ON mydb.* TO 'myuser'@'127.0.0.1';
GRANT ALL ON mydb.* TO 'myuser'@'172.%';
```

Drop all three on teardown. Centralise the create-or-alter logic in one helper so the three rows don't drift. This parallels the PostgreSQL `pg_hba.conf` entry that permits `172.16.0.0/12` alongside `localhost` and `127.0.0.1/32`.

## `localhost` Rewrite: Match by Value, Not by Variable Name

When a containerised application needs to reach a host-side database, the deployer must rewrite `localhost`/`127.0.0.1` in the app's environment to `host.docker.internal`. A first-draft implementation whitelists specific env-var names (`DATABASE_URL`, `PGHOST`, `REDIS_URL`, …); this breaks for apps that introduce custom names (`GF_DATABASE_HOST`, `SMTP_HOST`, app-specific aliases) — the container sees the unrewritten `127.0.0.1` and fails.

**Fix:** match by *value* at host-boundary positions via regex, not by var name. The pattern must handle:

- `postgresql://u:p@127.0.0.1:5432/db` → `…@host.docker.internal:…`
- `redis://localhost:6379/0` → `redis://host.docker.internal:6379/0`
- Bare `127.0.0.1:5432` → `host.docker.internal:5432`
- Multi-host values like `127.0.0.1:26379,remote:26379` (only the first host rewrites)
- Leave substrings alone: `my-localhost-fallback` must not become `my-host.docker.internal-fallback`

A regex anchored at URL schemes, `@host:port`, bare `host:port`, and full-value hosts covers this. Whitelists are a design smell — whenever you see one, ask what the general rule is. Unit-test both positive and negative cases.

## Unix Socket Authentication

Homebrew-installed MariaDB on macOS uses unix socket authentication. The `root` user cannot connect via TCP. Only the current OS user can connect via the socket at `/tmp/mysql.sock`.

Admin tooling that defaults to `root@127.0.0.1` will fail. Auto-detect the socket and fall back to the OS username:

```python
# Common socket locations
SOCKET_PATHS = [
    "/tmp/mysql.sock",           # macOS Homebrew
    "/var/run/mysqld/mysqld.sock",  # Debian/Ubuntu
    "/var/lib/mysql/mysql.sock",    # RHEL/CentOS
]

# When using socket auth with no explicit config, use OS user
if unix_socket and superuser == "root" and not password:
    superuser = os.getenv("USER", "root")
```

## Environment Variable Naming

Different apps expect different env var names for the same database:

| Addon | Hop3 Injects | Django Expects | Node.js Expects | Go Expects |
|-------|-------------|----------------|-----------------|------------|
| PostgreSQL | `PGHOST`, `PGPORT`, `PGUSER`, `PGPASSWORD`, `PGDATABASE`, `DATABASE_URL` | `DATABASE_URL` | `DATABASE_URL` or `PGHOST`+... | `DATABASE_URL` |
| MySQL | `MYSQL_HOST`, `MYSQL_PORT`, etc. | `DATABASE_URL` | `MYSQL_HOST`+... | `DATABASE_URL` |
| Redis | `REDIS_URL`, `REDIS_HOST`, `REDIS_PORT` | `REDIS_URL` | `REDIS_URL` | `REDIS_URL` |

The `[env.computed]` feature solves the mapping problem:

```toml
[env.computed]
DB_HOST = "${PGHOST}"
DB_PORT = "${PGPORT}"
DATABASE_URL = "postgresql://${PGUSER}:${PGPASSWORD}@${PGHOST}:${PGPORT}/${PGDATABASE}"
```

## Env Var Update Semantics

By default, hop3.toml `[env]` values are treated as **defaults** — they only set vars that don't already exist. This preserves user-set values (via `config:set`) and addon values.

This is confusing when users change a value in hop3.toml and redeploy expecting it to take effect. The deploy log says "Set 0 env var(s)" with no explanation.

**Fix 1:** Log what was skipped: `Skipped 4 env var(s) already set: VAR1, VAR2`

**Fix 2:** Support override policy:

```toml
[env]
_policy = "override"  # Force hop3.toml values on every deploy
DEBUG = "false"
```

## Connection String Formats

Always inject BOTH individual variables AND a connection URL. Different frameworks expect different formats:

```
DATABASE_URL=postgresql://user:pass@127.0.0.1:5432/mydb
PGHOST=127.0.0.1
PGPORT=5432
PGUSER=user
PGPASSWORD=pass
PGDATABASE=mydb
```

Rails and Django use `DATABASE_URL`. Psycopg2 uses `PG*` variables. Some Go libraries use the URL, others use individual vars. Injecting both covers all cases.
