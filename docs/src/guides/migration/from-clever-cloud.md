# Migrating from Clever Cloud to Hop3

Clever Cloud already gives you a European PaaS, so this isn't a sovereignty story. It's a cost-and-control story. When the per-application runtime billing stops matching what the workload actually needs, or you want the whole stack on infrastructure you own and can move, Hop3 gives you the same `git push` deployment experience on a server you control. This guide helps you migrate existing Clever Cloud apps to Hop3.

## What's Similar

If you're comfortable on Clever Cloud, the Hop3 workflow will feel familiar:

| Clever Cloud | Hop3 |
|--------------|------|
| `git push clever master` | `git push hop3 main` |
| Runtime auto-detection | Native auto-detection |
| `clever env set` | `hop3 env set` |
| `clever addon create` | `hop3 addon create` |
| `clever logs` | `hop3 app logs` |
| `clever scale` | `hop3 ps scale` |

You push a Git repository, the platform inspects your stack and builds it, and a reverse proxy fronts the result. Both platforms detect the runtime from your project files rather than asking you to hand-write a build pipeline.

One syntactic difference to keep in mind: where the `clever` CLI takes the app implicitly from the linked directory (`clever link`), Hop3 targets an app with the `--app` flag rather than a positional argument. So `clever env set FOO bar` becomes `hop3 env set FOO=bar --app myapp`. (Hop3 can also resolve the app from a `hop3.toml` in the current directory, so once your repo has one, `--app` is usually optional.)

## What's Different

| Clever Cloud | Hop3 |
|--------------|------|
| Managed platform | Self-hosted |
| Vertical + horizontal auto-scalers | Single server, manual scaling |
| Broad addon catalogue | PostgreSQL, MySQL, Redis, S3/MinIO — and growing |
| `CC_*` runtime knobs | `hop3.toml` + `[env]` |
| Multi-instance, multi-zone | One server you manage |

The biggest difference is scaling. Clever Cloud's vertical scaler resizes an instance and its horizontal scaler adds instances automatically as load rises. Hop3 runs on a single server and scales **manually**: you set the process count yourself with `hop3 ps scale`. There is no autoscaler, no edge, no multi-region. If automatic burst handling is load-bearing for your app, weigh that before you move.

Hop3 is simpler in exchange. You manage one server instead of a fleet, and you own every layer of it.

## Step 1: Set Up Your Hop3 Server

Provision a server (Ubuntu 24.04 LTS or newer recommended; Debian, Fedora, and Rocky/Alma also work) and install Hop3:

```bash
ssh root@your-server.com
curl -LsSf https://hop3.cloud/install-server.py | sudo python3 -
```

Install the CLI on your local machine:

```bash
hop3-install cli
```

Connect the CLI to your server. On a first install this also creates the
admin account and stores your API token:

```bash
hop3 init --ssh root@your-server.com
```

## Step 2: Export Your Clever Cloud Configuration

Get your Clever Cloud environment variables from the linked app directory:

```bash
clever env > clever-env.txt
```

Review the file and remove Clever-specific variables — they map to Hop3 mechanisms rather than carrying over verbatim:

- `CC_*` build/run knobs (e.g. `CC_RUN_COMMAND`, `CC_PYTHON_VERSION`, `CC_PRE_BUILD_HOOK`) — these become `hop3.toml` sections, not environment variables. See Step 3.
- `POSTGRESQL_ADDON_URI` / `REDIS_URL` and similar addon URIs — Hop3 sets these for you when you attach an addon.
- `PORT` — auto-set by Hop3.

Keep your own application variables (secrets, feature flags, settings module, and so on).

## Step 3: Translate `CC_*` Knobs into hop3.toml

Clever Cloud configures the build and run through `CC_*` environment variables. Hop3 puts the same information in a `hop3.toml` file. There is no automatic importer for this translation — you do it by hand, and it's a short, mechanical mapping:

| Clever Cloud `CC_*` | hop3.toml |
|---------------------|-----------|
| `CC_RUN_COMMAND` | `[run]` start command / `Procfile` `web:` line |
| `CC_PRE_BUILD_HOOK` | `[build] before-build` |
| `CC_POST_BUILD_HOOK` | `[build] after-build` |
| `CC_PRE_RUN_HOOK` | `[run] before-run` |
| `CC_PYTHON_VERSION` / language version | system runtime, or `[build] builder = "docker"` for a pinned version |
| `CC_WORKER_COMMAND` / extra processes | `[run.workers]` |

A representative Python app that on Clever Cloud relied on `CC_PRE_BUILD_HOOK="npm install && npm run build"`, `CC_PRE_RUN_HOOK="python manage.py migrate"`, and a worker, becomes:

```toml
[metadata]
id = "your-app"

[build]
toolchain = "python"
before-build = "npm install && npm run build"

[env]
# Copy your own variables from clever-env.txt
SECRET_KEY = "your-secret-key"
DJANGO_SETTINGS_MODULE = "myapp.settings.production"
HOST_NAME = "your-app.example.com"

[run]
before-run = ["python manage.py migrate"]

[run.workers]
worker = "celery -A myapp worker"

[healthcheck]
path = "/health/"
```

If you already deploy with a `Procfile`, Hop3 reads it directly for the process model — and you can convert it to a starter `hop3.toml` with:

```bash
hop3 app migrate procfile .
```

This is the only configuration importer Hop3 ships. There is no importer for `clever.json` or other PaaS manifests; the `CC_*` mapping above is done by hand.

## Step 4: Migrate Your Database

Clever Cloud exposes the database connection through an addon URI (for PostgreSQL, `POSTGRESQL_ADDON_URI`).

### Export from Clever Cloud

Read the URI from your environment and dump with the standard tools:

```bash
# The URI is in your Clever Cloud env (POSTGRESQL_ADDON_URI)
pg_dump --no-owner --format=custom \
    "$POSTGRESQL_ADDON_URI" > latest.dump
```

### Import to Hop3

First, create the database addon and attach it to your app:

```bash
hop3 addon create postgres your-app-db
hop3 addon attach your-app-db --app your-app
```

Get the connection details:

```bash
hop3 addon show your-app-db
```

Import the dump:

```bash
# Copy dump to server
scp latest.dump root@your-server.com:/tmp/

# SSH to server and import
ssh root@your-server.com
sudo -u postgres pg_restore --verbose --no-owner \
    -d your_app_db /tmp/latest.dump
```

Hop3's four addon types are PostgreSQL, MySQL, Redis, and S3/MinIO — and growing. If you depend on a Clever Cloud addon Hop3 doesn't offer, you have two options: keep that managed service and point `[env]` at its URL, or run the dependency yourself. There is no in-platform equivalent for the broader Clever Cloud addon catalogue.

## Step 5: Deploy to Hop3

Add Hop3 as a remote:

```bash
git remote add hop3 hop3@your-server.com:your-app
```

Deploy:

```bash
git push hop3 main
```

You can also deploy from the working directory with `hop3 deploy` if you prefer not to push over Git.

## Step 6: Point Your Domain

Update your DNS:

```
your-app.example.com  A  your-server-ip
```

Bind the hostname to the app:

```bash
hop3 domain add your-app.example.com --app your-app
```

Once Let's Encrypt / ACME is configured on the server, Hop3 requests a certificate for the domain at deploy time. Out of the box, a freshly installed server serves a self-signed certificate until you point it at an ACME provider.

## Common Migration Issues

### Runtime Detection vs `CC_*`

Clever Cloud reads `CC_*` variables to decide how to build and start. Hop3 auto-detects the toolchain (Python, Node.js, Go, Ruby, Rust, Java, PHP, Elixir, .NET) from your project files, and you only reach for `[build]` / `[run]` when the defaults aren't right. Most apps need just `[metadata].id` plus their own `[env]`.

### Runtime Versions

Clever Cloud pins the language version with a `CC_*` variable (e.g. `CC_PYTHON_VERSION`). Hop3 uses the system runtime that ships with the OS. For a specific, reproducible version, use the Docker builder:

```toml
[build]
builder = "docker"
```

A Nix builder is also available when you want fully reproducible builds.

### Multi-Language Builds

For an app that needs a second toolchain (e.g. Python plus a Node asset build), use the `[build]` section instead of a Clever build hook:

```toml
[build]
toolchain = "python"
before-build = "npm install && npm run build"
```

### Postgres Extensions

If your app relies on a Postgres extension (like `pg_stat_statements`), enable it through the addon command — no SSH or manual `psql` needed:

```bash
hop3 addon postgres extensions your-app-db pg_stat_statements
```

Extensions are allow-listed, so only the ones Hop3 ships support for will install.

### Scaling

Clever Cloud's scalers move automatically. On Hop3 you set the process count yourself:

```bash
hop3 ps scale your-app web=3 worker=2
```

There is no autoscaler. Size the server for your peak, and adjust `ps scale` when the workload changes. This is the migration's main trade-off — plan for it rather than discovering it under load.

### Scheduled Jobs

For periodic work, declare a worker:

```toml
[run.workers]
scheduler = "celery -A myapp beat"
```

Or use system cron on the server directly.

## Command Mapping

| Clever Cloud Command | Hop3 Command |
|----------------------|--------------|
| `clever create` | `hop3 app create` |
| `clever applications` | `hop3 app list` |
| `clever status` | `hop3 app status --app X` |
| `clever env` | `hop3 env show --app X` |
| `clever env set` | `hop3 env set K=V --app X` |
| `clever logs` | `hop3 app logs --app X` |
| `clever ssh` | `hop3 app run --app X` |
| `clever scale` | `hop3 ps scale --app X web=N` |
| `clever restart` | `hop3 app restart --app X` |
| `clever addon create` | `hop3 addon create <type> <name>` |
| `clever addon` | `hop3 addon show <name>` |
| `clever stop` | `hop3 app stop --app X` |

## Cost and Lock-In

Clever Cloud already keeps your data in the EU, so the move isn't about jurisdiction. It's about two things: a predictable bill and total control of the stack.

On Clever Cloud you pay per running instance and per addon, and the auto-scalers can grow that bill on their own as traffic moves. On Hop3 you pay for one VPS. A small app that costs roughly the price of a couple of instances plus a database addon on Clever Cloud runs on a ~10 EUR/month VPS; a medium app on a ~30 EUR/month VPS. The trade-off is that the elastic headroom the scalers gave you is now your job to provision.

The deeper win is lock-in. Your app is a Git repository plus a `hop3.toml`, your data is a standard `pg_dump`, and your server is a plain VPS you can image and move to any provider. Nothing about the deployment is specific to one vendor's control plane.

## Rollback Plan

Keep your Clever Cloud app running during migration:

1. Deploy to Hop3 with a test domain.
2. Verify everything works — including database imports and worker processes.
3. Switch DNS to Hop3.
4. Keep the Clever Cloud app running for 1-2 weeks.
5. Delete the Clever Cloud app and its addons once you're confident.

## Getting Help

- [Hop3 Documentation](https://hop3.cloud)
- [GitHub Issues](https://github.com/abilian/hop3/issues)
- [Troubleshooting Guide](/guides/troubleshooting/)

---

*Coming from a different platform? The concepts are similar. Check the [Getting Started guide](/get-started/) for a fresh start.*
