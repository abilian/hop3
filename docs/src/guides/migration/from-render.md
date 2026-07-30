# Migrating from Render to Hop3

Render made the right first impression: connect a GitHub repo, get a `render.yaml`, push, and your service is live. The trouble usually starts later — the free tier shrank, free web services spin down and cold-start on the next request, and as soon as you add a paid instance plus a managed Postgres plus a Redis, the monthly bill creeps past what a single VPS costs outright. If what you want is a predictable fixed-cost box that you control, Hop3 gives you the same git-push, declarative-config, managed-addons experience on your own server. This guide helps you migrate a Render service to Hop3.

## What's Similar

Hop3 and Render share the same shape: a declarative file in the repo, addons for databases and caches, and deploy-on-push.

| Render | Hop3 |
|--------|------|
| Auto-deploy on `git push` to GitHub | `git push hop3 main` |
| `render.yaml` Blueprint | `hop3.toml` |
| Build & start commands | `[build]` / `[run]` (or a `Procfile`) |
| Managed Postgres / Redis | `hop3 addon create` |
| Env groups | `[env]` |

The mental model carries over. A Render *service* is a Hop3 *app*; the build and start commands you set in the dashboard (or in `render.yaml`) become the `[build]` and `[run]` sections of `hop3.toml`; your env group becomes `[env]`.

One workflow difference to keep in mind: Render auto-deploys whenever you push to the connected GitHub branch. Hop3 deploys when you push to its own remote — `git push hop3 main` — so deploying stays an explicit act rather than a side effect of pushing to GitHub. The app you're targeting in CLI commands is always the `--app` flag, never a positional argument: `hop3 env set FOO=bar --app myapp`.

## What's Different

| Render | Hop3 |
|--------|------|
| Managed platform | Self-hosted |
| Autoscaling | Manual scaling (`hop3 ps scale`) |
| Many service types + many addons | One app model; PostgreSQL, MySQL, Redis, S3/MinIO — and growing |
| Preview environments | Not yet supported (use staging apps) |
| Multi-region | Single server |

Hop3 is simpler. You manage one server instead of an opaque cloud, and you trade some managed conveniences (preview environments, autoscaling) for full control and a fixed bill.

## Mapping Render Services to Hop3

Render's Blueprint groups several `type:` services under one `render.yaml`. Each maps cleanly onto a Hop3 concept:

| Render service `type` | Hop3 equivalent |
|-----------------------|-----------------|
| `web` | A Hop3 app with a `web` process (`[run].start` / Procfile `web`) |
| `worker` | A `[run.workers]` entry on the same app |
| `cron` | A `[run.workers]` entry, or a system cron job |
| `pserv` (private service) | A Hop3 app not bound to a public domain, or an addon |
| `static` (static site) | The static builder (`[build] toolchain = "static"`) |
| Managed `pserv` Postgres / Redis | `hop3 addon create postgres|redis …` |
| Env group | `[env]` in `hop3.toml` |

A multi-service Render Blueprint becomes one Hop3 app whose web, worker, and cron processes live together (web + workers in one app), plus addons for the databases. A standalone static site is its own Hop3 app using the static builder.

## Step 1: Set Up Your Hop3 Server

Provision a server (Ubuntu 24.04 LTS recommended; Debian, Fedora, and Rocky/Alma also work) and install Hop3:

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

## Step 2: Export Your Render Configuration

Render keeps your environment in env groups and on the service itself, in the dashboard. Copy the variables you need from the Render dashboard (Environment tab, and any linked env groups) into a local file, then drop the ones Hop3 manages for you:

- `DATABASE_URL` (will be set by the Hop3 Postgres addon)
- `REDIS_URL` (will be set by the Hop3 Redis addon)
- `PORT` (auto-set by Hop3 — your app should bind `$PORT`)
- `RENDER_*` variables (Render-internal, not portable)

What's left — your `SECRET_KEY`, third-party API keys, feature flags — becomes your `[env]` block in the next step.

## Step 3: Translate render.yaml to hop3.toml

Here is a representative Render Blueprint — a Python web service with a background worker and a daily cron, plus a managed Postgres and Redis:

```yaml
# render.yaml
services:
  - type: web
    name: myapp
    runtime: python
    buildCommand: "pip install -r requirements.txt && python manage.py collectstatic --noinput"
    startCommand: "gunicorn myapp.wsgi"
    envVars:
      - key: DJANGO_SETTINGS_MODULE
        value: myapp.settings.production
      - fromGroup: myapp-secrets

  - type: worker
    name: myapp-worker
    runtime: python
    startCommand: "celery -A myapp worker"

  - type: cron
    name: myapp-cleanup
    runtime: python
    schedule: "0 3 * * *"
    startCommand: "python manage.py cleanup"

databases:
  - name: myapp-db
```

The equivalent `hop3.toml` collapses the web, worker, and cron services into a single app, and turns the managed database into an addon you create separately (Step 4):

```toml
[metadata]
id = "myapp"

[build]
toolchain = "python"
before-build = "python manage.py collectstatic --noinput"

[env]
# Variables from your Render env group / service
DJANGO_SETTINGS_MODULE = "myapp.settings.production"
SECRET_KEY = "your-secret-key"

[run]
start = "gunicorn myapp.wsgi"
before-run = ["python manage.py migrate"]

[run.workers]
worker = "celery -A myapp worker"

[healthcheck]
path = "/health/"
```

A couple of translation notes:

- Render's `buildCommand` splits into `[build]`. Dependency installation is automatic (Hop3 detects `requirements.txt`), so only the *extra* build steps — like `collectstatic` — go in `before-build`.
- Render's `startCommand` becomes `[run].start` (equivalently the `web` line of a `Procfile`).
- The Render `worker` service becomes a `[run.workers]` entry on the same app, so it shares the app's code and environment.
- The Render `cron` service has two homes in Hop3 — see Step 5.
- `[healthcheck]` is the Hop3 equivalent of a Render health check path; it also accepts `timeout` and `retries`.

## Step 4: Migrate Your Database

### Export from Render

Render gives you an external connection string for a managed database (Dashboard → your database → Connect → External Connection). Dump it with the standard tools:

```bash
pg_dump "$RENDER_EXTERNAL_DATABASE_URL" -Fc -f latest.dump
```

### Import to Hop3

Create the database addon and attach it to your app:

```bash
hop3 addon create postgres myapp-db
hop3 addon attach myapp-db --app myapp
```

Get the connection details:

```bash
hop3 addon show myapp-db
```

Import the dump:

```bash
# Copy dump to server
scp latest.dump root@your-server.com:/tmp/

# SSH to server and import
ssh root@your-server.com
sudo -u postgres pg_restore --verbose --no-owner \
    -d myapp_db /tmp/latest.dump
```

Once the addon is attached, Hop3 injects `DATABASE_URL` into the app automatically — that's why you removed it from your env in Step 2.

### Postgres Extensions

If your Render database used extensions (like `pg_stat_statements` or `pgcrypto`), enable them through the addon command — no SSH or manual `psql` needed:

```bash
hop3 addon postgres extensions myapp-db pg_stat_statements
```

Extensions are allow-listed, so only the ones Hop3 ships support for will install.

### Redis

Add a Redis addon the same way:

```bash
hop3 addon create redis myapp-cache
hop3 addon attach myapp-cache --app myapp
```

Most Render Redis instances hold cache data, so starting fresh is usually fine — the addon injects `REDIS_URL` and your app repopulates the cache on its own. If you need to carry data across, dump and restore it explicitly.

### Keeping a managed database (optional)

If you'd rather not move the data yet, you can keep an external managed database and just point Hop3 at it: set its connection string under `[env]` (e.g. `DATABASE_URL = "postgresql://…"`) instead of creating an addon. You lose Hop3's backup integration for that database, but it's a clean way to migrate the app first and the data later.

## Step 5: Scheduled Jobs

Render's `cron` service type doesn't have a direct managed equivalent, but you have two options.

A long-lived scheduler (Celery beat, APScheduler) is just another worker:

```toml
[run.workers]
scheduler = "celery -A myapp beat"
```

For a plain "run this command at 03:00" job — the closest match to a Render cron — use system cron on the server:

```bash
ssh root@your-server.com
crontab -e
# Add: 0 3 * * * /home/hop3/apps/myapp/venv/bin/python /home/hop3/apps/myapp/src/manage.py cleanup
```

## Step 6: Deploy to Hop3

Add Hop3 as a remote and push:

```bash
git remote add hop3 hop3@your-server.com:myapp
git push hop3 main
```

You can also deploy from a working directory with `hop3 deploy`. The deploy uploads your source, detects the toolchain, builds, configures the reverse proxy, and starts the web process and any workers — the equivalent of a Render Blueprint sync, but triggered on your terms.

## Step 7: Point Your Domain

Render gives every service an `onrender.com` subdomain and lets you add custom domains in the dashboard. On Hop3 you bind hostnames to the app — declaratively in `hop3.toml`:

```toml
[domains]
list = ["myapp.example.com", "www.myapp.example.com"]
```

Then update your DNS to point at the server:

```
myapp.example.com  A  your-server-ip
```

Out of the box, a freshly installed server serves a self-signed certificate. Once Let's Encrypt / ACME is configured on the server, Hop3 requests a real certificate for the domain at deploy time.

## Static Sites

A Render static site maps onto Hop3's static builder. There's no app process — nginx serves the files straight from disk:

```toml
[metadata]
id = "myapp-site"

[build]
toolchain = "static"
before-build = "npm ci && npm run build"
static-dir = "dist"
```

`before-build` runs your build step (Render's `buildCommand`); `static-dir` is the output directory to serve (Render's "Publish Directory").

## Command Mapping

| Render | Hop3 |
|--------|------|
| Dashboard service list | `hop3 app list` |
| Create a service (from Blueprint) | `hop3 app create` |
| Service detail page | `hop3 app status --app X` |
| Environment tab | `hop3 env show --app X` |
| Set an env var | `hop3 env set K=V --app X` |
| Logs tab | `hop3 app logs --app X` |
| Instance count | `hop3 ps --app X` |
| Scale instances | `hop3 ps scale --app X web=N` |
| Manual deploy / restart | `hop3 app restart --app X` |
| Shell tab | `hop3 app run --app X` |
| Managed database list | `hop3 addon list` |
| Database detail | `hop3 addon show <name>` |
| Suspend a service | `hop3 app stop --app X` |

## Cost and Lock-in

Render's pricing is reasonable per line item, but it compounds: a paid web instance, a paid worker, a managed Postgres, and a managed Redis are four separate meters. The free tier exists, but free web services spin down when idle and cold-start on the next request — fine for a demo, frustrating for anything real.

| | Render | Hop3 (self-hosted) |
|-|--------|--------------------|
| Web instance (Starter) | ~$7/month | - |
| Background worker (Starter) | ~$7/month | - |
| Managed Postgres (Basic) | ~$19/month | - |
| Managed Redis (Starter) | ~$10/month | - |
| **Total (this example)** | ~$43/month | ~$10–30/month (one VPS) |

The numbers move with your plan, but the structure is the point: on Render you pay per service and per addon; on Hop3 the web process, the worker, the cron, Postgres, and Redis all run on one box you rent at a fixed price. The trade-off is real — you own the server, the OS updates, and the backups. The upside is no per-meter creep, no cold starts, and a `hop3.toml` that runs anywhere Hop3 runs, so you're not locked to one provider's Blueprint format.

## Where Hop3 Falls Short of Render

Be clear-eyed about what you give up:

- **Preview environments.** Render spins up a temporary environment per pull request. Hop3 has no equivalent yet. The workaround is a manually deployed staging app — deploy a second app named `myapp-staging` (or a per-branch `myapp-feature-x`) and point a test domain at it.
- **Autoscaling.** Render can scale instance count automatically under load. Hop3 scaling is manual: `hop3 ps scale --app myapp web=3 worker=2`. You set the process counts; the platform doesn't change them for you.
- **Single server.** There's no multi-region, no managed cluster, no edge. Hop3 runs your apps on one server you provision.
- **MFA.** Multi-factor auth on the Hop3 control plane is deferred.

None of these block a typical small-to-medium service migration, but if preview environments or autoscaling are load-bearing in your workflow, plan for the gap before you switch.

## Rollback Plan

Keep your Render service running during the migration:

1. Deploy to Hop3 with a test domain.
2. Verify the app, its workers, and its scheduled jobs all run.
3. Switch DNS to the Hop3 server.
4. Keep the Render service (and its database) running for 1–2 weeks.
5. Suspend, then delete, the Render service once you're confident.

Because Hop3 deploys on an explicit `git push hop3` rather than on every GitHub push, you can keep pushing to GitHub (and to Render) throughout, and only cut over when the Hop3 deployment has proven itself.

## Getting Help

- [Hop3 Documentation](https://hop3.cloud)
- [GitHub Issues](https://github.com/abilian/hop3/issues)
- [Troubleshooting Guide](/guides/troubleshooting/)

---

*Coming from a different platform? The concepts are similar. Check the [Getting Started guide](/get-started/) for a fresh start.*
