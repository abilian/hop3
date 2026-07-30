# Migrating from Azure App Service to Hop3

Thinking about leaving Azure App Service? Whether it's the cost curve, the lock-in, or simply wanting your own box, Hop3 gives you a familiar deploy-from-git workflow on infrastructure you control. This guide helps you move an existing App Service web app to Hop3.

The pitch in one sentence: on App Service you rent a managed runtime and pay per plan tier; on Hop3 you run the same app on a server you own, and it stays up without an Always-On toggle to pay for.

## What's Similar

If you've been deploying with App Service's deployment center, the Hop3 loop will feel familiar:

| Azure App Service | Hop3 |
|-------------------|------|
| Git / GitHub Actions deploy | `git push hop3 main` |
| Startup command | `Procfile` / `[run]` |
| App settings | `hop3 env set` |
| Connection strings | `[env]` / addon connection vars |
| Custom domain + managed cert | `hop3 domain add` + Hop3 ACME |

You still push code from git and the platform builds it. A `Procfile` is supported for the process model, so if you already have one it carries over.

One syntactic habit to retrain: App Service's app target is the resource you select in the portal or pass with `--name`. In Hop3 the app you're targeting is always the `--app` flag, never a positional or colon syntax. So a settings change like `az webapp config appsettings set --name myapp --settings FOO=bar` becomes `hop3 env set FOO=bar --app myapp`.

## What's Different

| Azure App Service | Hop3 |
|-------------------|------|
| Managed platform | Self-hosted |
| Autoscale (rules / metrics) | Manual scaling (`ps scale`) |
| Many backing services | PostgreSQL, MySQL, Redis, S3/MinIO — and growing |
| Deployment slots | Not supported (use a separate staging app) |
| Always-On toggle | Always on (no toggle) |
| WebJobs | `[run.workers]` or system cron |

Hop3 is simpler. You manage one server instead of an App Service plan, a region, and a sprawl of resource settings. The trade-off is real and worth stating up front: there are no deployment slots and no autoscale. Both have plain workarounds, covered below.

## Step 1: Set Up Your Hop3 Server

Provision a server (Ubuntu 24.04 LTS or newer recommended; Debian, Fedora, and Rocky/Alma are also supported) and install Hop3:

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

## Step 2: Export Your App Service Configuration

App Service keeps two things you need: **app settings** (plain environment variables) and **connection strings** (database/cache/storage endpoints). Both surface to your app as environment variables, so both become `[env]` entries in Hop3.

Export the app settings:

```bash
az webapp config appsettings list --name your-app \
    --resource-group your-rg -o tsv > azure-appsettings.txt
```

And the connection strings:

```bash
az webapp config connection-string list --name your-app \
    --resource-group your-rg -o tsv > azure-connstrings.txt
```

Review both files and drop the App Service-managed and infrastructure entries:

- `WEBSITES_PORT` / `PORT` (Hop3 sets `PORT` automatically)
- `WEBSITE_*` variables (App Service runtime internals)
- `SCM_*` / `DOCKER_*` deployment-center variables
- Any connection string you intend to replace with a Hop3 addon (see Step 4)

Note your **startup command** too — App Service stores it under the runtime stack settings (the "Startup Command" field, or `az webapp config show --query appCommandLine`). That string becomes your `web` process in a `Procfile` or `[run]`.

## Step 3: Add hop3.toml

A `Procfile` is supported, but `hop3.toml` gives you more control. The mapping from App Service primitives is direct:

- **Runtime stack** (e.g. "Python 3.12", "Node 20", ".NET 8") → Hop3's native toolchain, auto-detected from your repo. Native auto-detection covers Python, Node.js, Go, Ruby, Rust, Java, PHP, Elixir, and .NET.
- **Startup command** → the `web` line of your `Procfile`, or `[run]`.
- **App settings + connection strings** → `[env]`.
- **WebJobs** → `[run.workers]` (long-running) or system cron (scheduled).

```toml
[metadata]
id = "your-app"

[env]
# From azure-appsettings.txt and azure-connstrings.txt
SECRET_KEY = "your-secret-key"
DJANGO_SETTINGS_MODULE = "myapp.settings.production"
HOST_NAME = "your-app.example.com"

[run]
before-run = ["python manage.py migrate"]

[healthcheck]
path = "/health/"
```

If you had an App Service startup command rather than a framework Hop3 can launch on its own, express it as a `Procfile` and let Hop3 read the process model from it:

```
web: gunicorn myapp.wsgi --bind 0.0.0.0:$PORT
```

There is no importer for App Service configuration — App Service has no portable config file to read. The only config importer Hop3 ships converts a `Procfile` to `hop3.toml`:

```bash
cd your-app/
hop3 app migrate procfile .
```

Everything else in this post (app settings, connection strings, the startup command, WebJobs) is translated by hand into the `hop3.toml` shown above. That hand mapping *is* the migration.

## Step 4: Migrate Your Database

App Service itself doesn't host your database — it points at Azure Database for PostgreSQL, Azure Database for MySQL, or another store via a connection string. You have two clean choices.

### Option A: Keep the external managed database

If you want to keep Azure Database (or any managed DB) for now, don't migrate the data at all — just point Hop3 at the same URL:

```bash
hop3 env set --app your-app \
    DATABASE_URL=postgresql://user:pass@your-db.postgres.database.azure.com/yourdb
```

This is the lowest-risk first move: switch where the app *runs* without touching where the data *lives*.

### Option B: Move the data onto a Hop3 addon

To leave Azure entirely, dump from Azure Database and load into a Hop3 PostgreSQL addon. Hop3's addons today are PostgreSQL, MySQL, Redis, and S3/MinIO — and growing.

Dump from Azure Database for PostgreSQL:

```bash
pg_dump --no-owner --format=custom \
    "host=your-db.postgres.database.azure.com user=adminuser dbname=yourdb sslmode=require" \
    > latest.dump
```

Create the addon and attach it:

```bash
hop3 addon create postgres your-app-db
hop3 addon attach your-app-db --app your-app
```

Attaching injects the connection variables (`DATABASE_URL`, …) into the app. Get the connection details:

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

For MySQL, the shape is identical: dump from Azure Database for MySQL with `mysqldump`, `hop3 addon create mysql your-app-db`, attach, then load the dump.

If your app uses Postgres extensions, enable them through the addon command — no SSH or manual `psql`:

```bash
hop3 addon postgres extensions your-app-db pg_stat_statements
```

Extensions are allow-listed, so only the ones Hop3 ships support for will install.

## Step 5: Deploy to Hop3

Add Hop3 as a remote:

```bash
git remote add hop3 hop3@your-server.com:your-app
```

Deploy:

```bash
git push hop3 main
```

## Step 6: Point Your Domain

Bind your custom domain to the app:

```bash
hop3 domain add your-app.example.com --app your-app
```

Update your DNS to point at the server:

```
your-app.example.com  A  your-server-ip
```

App Service issues a managed certificate for custom domains. Hop3 does the equivalent at deploy time: once Let's Encrypt/ACME is configured on the server, Hop3 requests a certificate for the domain when you deploy. Out of the box, a freshly installed server serves a self-signed certificate until you point it at an ACME provider.

## Common Migration Issues

### Runtime Stacks vs Toolchains

App Service picks a runtime stack; Hop3 auto-detects a toolchain from the files in your repo. Most apps work unchanged:

| App Service Runtime Stack | Hop3 Toolchain |
|---------------------------|----------------|
| Python | `python` (auto-detected) |
| Node | `node` (auto-detected) |
| .NET | `.NET` (auto-detected) |
| Multi-step build | Use `[build]` section |

For apps that need an asset build step (e.g. Python plus a Node frontend), do it in `[build]`:

```toml
[build]
toolchain = "python"
before-build = "npm install && npm run build"
```

If you need a runtime version that differs from the server's, or you were running a custom container on App Service, use the Docker builder:

```toml
[build]
builder = "docker"
```

A Nix builder and a static-site builder are also available.

### Startup Command

App Service's startup command becomes the `web` process. If your framework is one Hop3 detects (Django, Flask, Express, …) you can often drop the explicit command entirely and let the toolchain start it. When you do need to be explicit, put it in a `Procfile`:

```
web: gunicorn myapp.wsgi --bind 0.0.0.0:$PORT
```

Always bind to `$PORT` — Hop3 sets it, just as App Service set `WEBSITES_PORT`/`PORT` for you.

### WebJobs and Scheduled Work

App Service runs background work as WebJobs (continuous or triggered). Map them by kind:

Continuous WebJobs become long-running workers:

```toml
[run.workers]
worker = "celery -A myapp worker"
```

Scheduled / triggered WebJobs become cron. Use the worker form for a process-style scheduler:

```toml
[run.workers]
scheduler = "celery -A myapp beat"
```

Or use system cron directly for a plain command on a clock:

```bash
ssh root@your-server.com
crontab -e
# Add: 0 * * * * /home/hop3/apps/your-app/venv/bin/python /home/hop3/apps/your-app/src/manage.py cleanup
```

### Deployment Slots

This is the gap that matters most coming from App Service. Hop3 has **no deployment-slot equivalent** — no blue/green swap, no slot-scoped settings, no warm-up-then-swap.

The workaround is a separate staging app:

1. Deploy a second app, e.g. `your-app-staging`, from your release branch.
2. Verify it on a staging domain.
3. When it's good, deploy the same commit to `your-app`.

There is no atomic swap; you re-deploy the validated commit to the production app. For most teams a verified staging app plus the rollback plan below covers what slots were doing.

### Autoscale

App Service autoscale (rule- or metric-based) has no equivalent — Hop3 scaling is manual. Set process counts yourself with `ps scale`:

```bash
hop3 ps scale your-app web=3 worker=2
```

This is a single-server platform: there is no multi-region, no cluster, and no edge. If your App Service app genuinely relied on autoscaling across instances to absorb load, size the server for the peak and scale processes manually — and treat horizontal scale-out as something Hop3 doesn't do today.

## Command Mapping

| Azure App Service (`az webapp …`) | Hop3 Command |
|-----------------------------------|--------------|
| `az webapp create` | `hop3 app create` |
| `az webapp list` | `hop3 app list` |
| `az webapp show` | `hop3 app status --app X` |
| `az webapp config appsettings list` | `hop3 env show --app X` |
| `az webapp config appsettings set` | `hop3 env set K=V --app X` |
| `az webapp log tail` | `hop3 app logs --app X` |
| (instance count) | `hop3 ps --app X` |
| autoscale settings | `hop3 ps scale --app X web=N` |
| `az webapp restart` | `hop3 app restart --app X` |
| (Kudu / SSH console) | `hop3 app run --app X` |
| `az webapp config hostname add` | `hop3 domain add <host> --app X` |
| `az webapp stop` | `hop3 app stop --app X` |

## Cost and Lock-In

App Service bills per plan: you pay for the tier, for Always-On, often for a separate Azure Database, and for staging slots that ride on a higher tier. The number grows with each managed piece, and every one of those pieces is Azure-shaped — your config lives in the portal, not in a file you own.

On Hop3 the bill is your VPS. A small app that ran on a Basic/Standard plan plus a managed database fits comfortably on a modest single server; a medium app on a larger one. The configuration that used to live in App Service settings now lives in `hop3.toml`, committed alongside your code.

The trade-off is the same one this whole post circles: you manage the server, you give up slots and autoscale, and in exchange you own the box, own the config, and stop paying per managed primitive. The process is always on — there is no Always-On toggle to remember or to pay for.

## Rollback Plan

Keep your App Service app running during the migration so you always have a way back:

1. Deploy to Hop3 on a test domain (or `your-app-staging`).
2. Point Hop3 at the *same* Azure Database first (Step 4, Option A) so the data layer is identical while you validate the runtime.
3. Verify everything works against real data.
4. Switch DNS to Hop3.
5. Keep the App Service app running for 1–2 weeks.
6. Once you're confident, migrate the data off Azure Database (Step 4, Option B) if you want to leave Azure entirely, then decommission the App Service plan.

Because there's no atomic slot swap, the DNS cutover plus the kept-running App Service app *is* your blue/green: traffic moves when DNS moves, and reverting is a DNS change back.

## Getting Help

- [Hop3 Documentation](https://hop3.cloud)
- [GitHub Issues](https://github.com/abilian/hop3/issues)
- [Troubleshooting Guide](/guides/troubleshooting/)

---

*Coming from a different platform? The concepts are similar. Check the [Getting Started guide](/get-started/) for a fresh start.*
