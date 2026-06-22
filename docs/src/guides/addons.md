# Addons

Addons are backing services — databases, caches, object storage — that your app depends on. Hop3 manages their lifecycle (create, attach, detach, destroy) and injects the connection details into your app as environment variables on deploy.

This guide covers the four addons shipped in Hop3 0.5 — `postgres`, `mysql`, `redis`, and `s3` — plus the experimental `email` (SMTP relay) addon added in 0.7.

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

# Dump / restore (all four types support both)
hop3 addon postgres dump my-database              # pg_dump → server backup dir
hop3 addon postgres restore my-database <path>    # psql restore (prompts)
hop3 addon mysql dump legacy-db
hop3 addon redis dump my-cache
hop3 addon redis restore my-cache <path>

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

**Docker apps:** Hop3 grants MySQL access on multiple host patterns (`@'localhost'`, `@'127.0.0.1'`, `@'10.%'`, `@'172.%'`, `@'192.168.%'`) so apps reaching the host MySQL from any of the private ranges a Docker network might use authenticate correctly. This is automatic, but it's worth knowing if you inspect the `mysql.user` table.

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

### email (experimental)

> **Experimental (0.7).** The command surface is marked subject to change and may evolve after real use. Every `addon email` command prints a one-line experimental banner.

Hop3 never runs a mail server — deliverability, IP reputation, and abuse make it a losing game, and most clouds block outbound port 25. The email addon stores your existing provider's **SMTP submission credentials** and injects them into attached apps. It is **outbound transactional email only**: no inbound, IMAP, or MX.

Because no two frameworks read the same variable names, the addon injects one transport under every common spelling, so a stock Django, Flask, or Node app sends mail with no code change.

**Configure it** — with any SMTP provider (Resend, Amazon SES, Postmark, Brevo, Mailgun, a corporate relay, …). Unlike the other addons, email is configured with a type-specific command that carries the credentials, not the generic `addon create`:

```bash
hop3 addon email create mail \
    --smtp-host smtp.resend.com \
    --smtp-user resend \
    --smtp-password @./smtp.secret \
    --from noreply@example.com
# --smtp-port defaults to 587 (STARTTLS); pass 465 for implicit TLS. Only 587/465.
```

Keep the password out of your shell history (ADR 036): `--smtp-password @<path>` reads it from a file, `--smtp-password -` reads it from stdin.

**Attach and check** (the type isn't inferred from the name, so pass `--type email`):

```bash
hop3 addon attach mail --app my-app --type email
hop3 addon email status mail            # shows host / port / from — never the password
```

**Injected env vars** — one transport, every common spelling:

| Variables | Consumer |
|-----------|----------|
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_TLS` | neutral / Node |
| `SMTP_URL` (`smtp://…:587` or `smtps://…:465`) | Node / nodemailer, URL parsers |
| `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS`, `EMAIL_USE_SSL`, `DEFAULT_FROM_EMAIL` | Django (`django.core.mail`) |
| `MAIL_SERVER`, `MAIL_PORT`, `MAIL_USERNAME`, `MAIL_PASSWORD`, `MAIL_USE_TLS`, `MAIL_USE_SSL`, `MAIL_DEFAULT_SENDER` | Flask-Mail |

So **Django**, **Flask-Mail**, and **Node/nodemailer** read their native names directly — no remapping.

**Frameworks that read no SMTP env** need one line of app-side glue (env injection can't reach them):

- **Rails (ActionMailer)** — in `config/environments/production.rb`:
  ```ruby
  config.action_mailer.smtp_settings = {
    address: ENV["SMTP_HOST"], port: ENV["SMTP_PORT"].to_i,
    user_name: ENV["SMTP_USER"], password: ENV["SMTP_PASSWORD"],
    authentication: :plain, enable_starttls_auto: true,
  }
  ```
- **WordPress** — stock `wp_mail()` uses PHP `mail()` and ignores env. Install an SMTP plugin (WP Mail SMTP, FluentSMTP) and point it at `SMTP_HOST` / `SMTP_PORT` / `SMTP_USER` / `SMTP_PASSWORD`, or map those into constants in `wp-config.php`.

> Email is configured imperatively, so don't declare it in `[[addons]]`: a declarative block has no credentials to provision, and the deploy fails loud telling you to run `addon email create`.

#### Deliverability is your job, at the provider

Hop3 only hands the message to your provider; whether it reaches the inbox is gated by DNS **on your sending domain**, not by Hop3:

- Publish **SPF**, **DKIM**, and **DMARC** for the From-domain at your provider (its dashboard generates the exact records). Since 2024, Gmail/Yahoo/Microsoft reject or spam-folder unauthenticated mail.
- The unit you authenticate is the **domain**, not the address. Once `example.com` is verified, any From on it — `noreply@`, `support@`, `billing@` — sends for free.
- Sending **as** `support@example.com` does not mean Hop3 hosts that mailbox; replies follow your domain's existing MX (Google Workspace, etc.).

`hop3 addon email create` and `hop3 addon email status` check **SPF and DMARC** for the domain via DNS and report what's missing — never claiming "ready" over unpublished records. DKIM and the exact per-provider SPF include are shown as guidance for now; auto-verifying those arrives with the named-provider profiles.

#### Wiring it into apps (recipes)

Attaching the addon injects the superset above. A few apps read those names directly; most read their own names and need a short `[env]` remap (Hop3's `${VAR}` interpolation, resolved *after* addon injection). Two recurring gotchas:

- **TLS flag:** the injected `SMTP_TLS` means **STARTTLS on 587**. Apps with an implicit-TLS/465 boolean or an enum (`EMAIL_SMTP_SECURE`, `SMTP_SECURE_ENABLED`, `SMTP_SECURITY`) should be set **literally** for a 587 relay — don't pipe `SMTP_TLS`.
- **Combined host:port:** Grafana and Gitea want one `host:port` string — splice it with `[env.computed]` (e.g. `GF_SMTP_HOST = "${SMTP_HOST}:${SMTP_PORT}"`).

**Works on attach (no remap):** BookWyrm, Bugsink (Django `EMAIL_*`).

**Laravel** (Monica, BookStack, Invoice Ninja):

```toml
[env]
MAIL_MAILER = "smtp"
MAIL_HOST = "${SMTP_HOST}"
MAIL_PORT = "${SMTP_PORT}"
MAIL_USERNAME = "${SMTP_USER}"
MAIL_PASSWORD = "${SMTP_PASSWORD}"
MAIL_ENCRYPTION = "tls"
MAIL_FROM_ADDRESS = "${SMTP_FROM}"   # BookStack uses MAIL_FROM instead
```

**Bespoke-prefix apps** — the `[env]` lines beyond a bare attach:

| App | `[env]` remap (values are `${SMTP_*}` unless quoted literal) |
|-----|-------------------------------------------------------------|
| GoToSocial | `GTS_SMTP_HOST`, `GTS_SMTP_PORT`, `GTS_SMTP_USERNAME=${SMTP_USER}`, `GTS_SMTP_PASSWORD`, `GTS_SMTP_FROM` |
| Vikunja | `VIKUNJA_MAILER_ENABLED="true"`, `_HOST`, `_PORT`, `_USERNAME=${SMTP_USER}`, `_PASSWORD`, `_FROMEMAIL=${SMTP_FROM}` |
| Forgejo / Gitea | `GITEA__mailer__ENABLED="true"`, `__PROTOCOL="smtp+starttls"`, `__SMTP_ADDR=${SMTP_HOST}`, `__SMTP_PORT`, `__USER`, `__PASSWD=${SMTP_PASSWORD}`, `__FROM=${SMTP_FROM}` |
| Discourse | `DISCOURSE_SMTP_ADDRESS=${SMTP_HOST}`, `_PORT`, `_USER_NAME=${SMTP_USER}`, `_PASSWORD`, `_ENABLE_START_TLS="true"`, `DISCOURSE_NOTIFICATION_EMAIL=${SMTP_FROM}` |
| Mattermost | `MM_EMAILSETTINGS_SMTPSERVER=${SMTP_HOST}`, `_SMTPPORT`, `_SMTPUSERNAME=${SMTP_USER}`, `_SMTPPASSWORD`, `_ENABLESMTPAUTH="true"`, `_CONNECTIONSECURITY="STARTTLS"`, `_SENDEMAILNOTIFICATIONS="true"`, `_FEEDBACKEMAIL=${SMTP_FROM}` |
| Mastodon | `SMTP_SERVER=${SMTP_HOST}`, `SMTP_LOGIN=${SMTP_USER}`, `SMTP_FROM_ADDRESS=${SMTP_FROM}` (`SMTP_PORT`/`SMTP_PASSWORD` already match) |
| Directus | `EMAIL_TRANSPORT="smtp"`, `EMAIL_SMTP_HOST=${SMTP_HOST}`, `_PORT`, `_USER=${SMTP_USER}`, `_PASSWORD`, `EMAIL_FROM=${SMTP_FROM}`, `EMAIL_SMTP_SECURE="false"` |
| Formbricks | core `SMTP_HOST/PORT/USER/PASSWORD` direct; add `MAIL_FROM=${SMTP_FROM}`, `SMTP_SECURE_ENABLED="0"` |
| Vaultwarden | `SMTP_HOST/PORT/FROM` direct; add `SMTP_USERNAME=${SMTP_USER}`, `SMTP_SECURITY="starttls"` |
| Grafana | `GF_SMTP_ENABLED="true"`, `GF_SMTP_USER=${SMTP_USER}`, `GF_SMTP_PASSWORD`, `GF_SMTP_FROM_ADDRESS=${SMTP_FROM}`, and `[env.computed] GF_SMTP_HOST="${SMTP_HOST}:${SMTP_PORT}"` |
| GlitchTip | `EMAIL_URL="smtp://${SMTP_USER}:${SMTP_PASSWORD}@${SMTP_HOST}:${SMTP_PORT}"` (URL-encode user/pass if they contain `@ : /`) |

> A few apps ship with their mailer toggled **off** in Hop3's generated config (Forgejo/Gitea `[mailer] ENABLED=false`, Vikunja `VIKUNJA_MAILER_ENABLED=false`); the remap above only takes effect once that default is cleared.

**Not yet reachable by env:** apps that read SMTP from a config file or DB — Nextcloud, Matrix-Synapse, MediaWiki, Keycloak, Wiki.js, Redmine, Dolibarr, Kanboard, LimeSurvey, Ghost — can't be wired by `[env]` today. They need a per-app config-file/post-deploy step; see the internal catalog-fit note.

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

When several addons of the same type are attached to one app, one is the primary and injects the canonical, unprefixed variables (`REDIS_URL`, etc.); each additional instance injects the same keys prefixed with its uppercased name (e.g. `JOB_QUEUE_REDIS_URL`). A single attached addon is always primary. Use `hop3 addon promote <name> --app <app>` to choose which instance is primary.

## Backup and Restore

Addons are included in app-level backups by default. See [Backup & Restore](backup-restore.md).

```bash
hop3 backup create --app my-app           # Includes attached addon data
hop3 backup create --app my-app --no-addons   # App code + env only
```

For a single addon, `hop3 addon <type> dump <name>` writes a standalone dump to the server's backup area, and `hop3 addon <type> restore <name> <path>` restores it. All four types support both verbs.

## See Also

- [hop3.toml reference: `[[addons]]`](../reference/config.md) — full schema
- [Backup & Restore](backup-restore.md)
- [Troubleshooting](troubleshooting.md)
