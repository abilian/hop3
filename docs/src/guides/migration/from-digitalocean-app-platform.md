# Migrating from DigitalOcean App Platform to Hop3

You're already on DigitalOcean. You like the dashboard, the networking, the backups, the predictable Droplet pricing. What stings is App Platform itself: every component is metered separately, a small app with a couple of services and a database climbs past what a single Droplet costs, and the managed convenience starts to feel like a tax. The good news is you don't have to leave DigitalOcean to leave App Platform. Install Hop3 on a Droplet you control, point your existing DigitalOcean infrastructure at it, and drop the per-component App Platform charges while keeping everything else you already pay for. This guide helps you migrate App Platform apps to Hop3.

## What's Similar

If you're comfortable with App Platform's app spec and `doctl`, Hop3 will feel familiar:

| DigitalOcean App Platform | Hop3 |
|---------------------------|------|
| GitHub auto-deploy on push | `git push hop3 main` |
| App spec (YAML) | `hop3.toml` |
| Buildpack auto-detection | Native toolchain auto-detection |
| `doctl apps create` | `hop3 app create` |
| Component env vars | `hop3 env set` |
| DO Managed Databases | `hop3 addon create` |

Push-to-deploy stays. Build detection stays — App Platform sniffs your repo for a buildpack, and Hop3 sniffs it for a toolchain. The mental model carries over.

One syntactic difference to keep in mind: App Platform centers on a single app spec describing many components, and `doctl apps` always takes an `--app-id`. In Hop3, each long-running service becomes its own app, and the app you're targeting is always the `--app` flag rather than a positional argument or an ID. So a `web` service in your spec becomes a Hop3 app, and you talk to it with `hop3 app status --app myapp`.

## What's Different

| DigitalOcean App Platform | Hop3 |
|---------------------------|------|
| Managed platform | Self-hosted (on your own Droplet) |
| Autoscaling (Pro tier) | Manual scaling (`hop3 ps scale`) |
| One spec, many components | One Hop3 app per service |
| Managed databases as a product | PostgreSQL, MySQL, Redis, S3/MinIO — and growing |
| Preview / branch deploys | Not yet supported |

Hop3 is simpler. You manage one server instead of a multi-component managed deployment — and that server is a Droplet you already understand.

## Mapping App Platform Components to Hop3

App Platform's central idea is the **component**. A single app spec bundles several component types, and each maps cleanly onto a Hop3 concept:

| App Platform component | Hop3 equivalent |
|------------------------|-----------------|
| `service` (long-running HTTP) | A Hop3 app (`web` process) |
| `static_site` | A Hop3 app with the static builder (`toolchain = "static"`) |
| `worker` (background process) | A `[run.workers]` entry in the same app |
| `job` (pre/post-deploy) | `[run] before-run`, or system cron for scheduled jobs |
| Buildpack build | Native toolchain (auto-detected) |
| Dockerfile build | `[build] builder = "docker"` |

The one shift worth internalizing: App Platform lets one spec describe a web service, a worker, and a static site as siblings under a single app. In Hop3, a **web service plus its background workers** live together in one app (the web process and its `[run.workers]`), while a **separate static site** is its own Hop3 app. Most App Platform apps are one service plus a database, so in practice you end up with one Hop3 app and one addon.

## Step 1: Set Up Your Hop3 Server

Provision a Droplet (Ubuntu 24.04 LTS recommended; Debian, Fedora, and Rocky/Alma also work) and install Hop3:

```bash
ssh root@your-droplet.example.com
curl -LsSf https://hop3.cloud/install-server.py | sudo python3 -
```

Install the CLI on your local machine:

```bash
hop3-install cli
```

Connect the CLI to your server. On a first install this also creates the
admin account and stores your API token:

```bash
hop3 init --ssh root@your-droplet.example.com
```

## Step 2: Export Your App Platform Configuration

Pull your current app spec so you have the component list and environment variables in front of you:

```bash
doctl apps spec get <your-app-id> > app-spec.yaml
```

Read through it and note, per component:
- Which component is the `service` (becomes your Hop3 app's `web` process)
- Which are `worker` components (become `[run.workers]`)
- Which are `static_site` components (become separate Hop3 apps)
- The `envs` block, minus anything App Platform injects for you

Strip the variables Hop3 sets itself before you copy them over:
- `DATABASE_URL` (will be set by the Hop3 addon, or pointed at your managed DB — see Step 4)
- `REDIS_URL` (will be set by the Hop3 addon)
- Bindable variables like `${db.DATABASE_URL}` and `${APP_URL}` (App Platform-specific)
- The HTTP port — App Platform passes `PORT`/`http_port`; Hop3 sets `$PORT` automatically

## Step 3: Add hop3.toml

App Platform keeps the app spec server-side; Hop3 keeps `hop3.toml` in your repo, next to your code. Translate the spec into a `hop3.toml`. A representative app — a Python web service with a background worker and a couple of env vars — looks like this:

```toml
[metadata]
id = "your-app"

[env]
# Copy plain envs from your app spec (drop the bindable ${...} ones)
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

The mapping back to your spec, line by line:

- The `service` component's run command becomes the `web` process (auto-detected from your framework, or set explicitly under `[run]`).
- Each `worker` component becomes one line under `[run.workers]`.
- A pre-deploy `job` becomes `before-run`.
- The component's `health_check.http_path` becomes `[healthcheck] path`.

### Buildpack app (the common case)

If App Platform builds your app from a buildpack, you usually need no `[build]` section at all — Hop3 auto-detects the toolchain (Python, Node.js, Go, Ruby, Rust, Java, PHP, Elixir, .NET) the same way the buildpack does:

| App Platform buildpack | Hop3 toolchain |
|------------------------|----------------|
| Python | `python` (auto-detected) |
| Node.js | `node` (auto-detected) |
| Go | `go` (auto-detected) |
| Ruby | `ruby` (auto-detected) |
| PHP | `php` (auto-detected) |

For an app that builds frontend assets at deploy time (e.g. Python plus a Node build step), use `before-build`:

```toml
[build]
toolchain = "python"
before-build = "npm install && npm run build"
```

### Dockerfile app

If your component sets `dockerfile_path` in the spec, you're building from a Dockerfile. Hop3 has a Docker builder — switch the builder and your existing Dockerfile is used as-is:

```toml
[build]
builder = "docker"
```

### Static site

If a component is a `static_site`, it becomes its own Hop3 app served straight from disk by nginx — no app process:

```toml
[metadata]
id = "your-site"

[build]
toolchain = "static"
static-dir = "build"   # the directory your build step emits (e.g. "dist", "public")
```

## Step 4: Migrate Your Database

You have two paths here. Pick based on how much you want to change at once.

### Option A — Keep your DigitalOcean Managed Database (low-risk on-ramp)

The least disruptive move: leave your DO Managed Database exactly where it is and point your Hop3 app at it. You keep DigitalOcean's managed backups and failover, and you only move the compute. Set the connection string in `[env]`:

```toml
[env]
DATABASE_URL = "postgresql://doadmin:password@your-db.db.ondigitalocean.com:25060/yourdb?sslmode=require"
```

Or set it with the CLI instead of committing it:

```bash
hop3 env set DATABASE_URL="postgresql://doadmin:...@your-db.db.ondigitalocean.com:25060/yourdb?sslmode=require" --app your-app
```

No data migration, no dump and restore — your data never moves. This is the recommended first step: cut over the app, prove it works against the database you already trust, and decide about the database later.

### Option B — Move the database into a Hop3 addon

When you're ready to consolidate everything onto the Droplet, create a Hop3 addon and migrate the data into it.

Export from your DO Managed Database with the standard PostgreSQL tools (the connection string is in the DigitalOcean control panel, or via `doctl databases connection`):

```bash
pg_dump "postgresql://doadmin:...@your-db.db.ondigitalocean.com:25060/yourdb?sslmode=require" \
    --no-owner --format=custom -f latest.dump
```

Create the addon and attach it:

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
scp latest.dump root@your-droplet.example.com:/tmp/

# SSH to server and import
ssh root@your-droplet.example.com
sudo -u postgres pg_restore --verbose --no-owner \
    -d your_app_db /tmp/latest.dump
```

Drop the `DATABASE_URL` you set in Option A — once the addon is attached, Hop3 injects the connection variables for you.

Hop3's addons are PostgreSQL, MySQL, Redis, and S3/MinIO (and growing). If App Platform was your front end to a DO Managed MySQL or Managed Redis (Valkey), those map to `hop3 addon create mysql ...` and `hop3 addon create redis ...` the same way — or keep them managed and point `[env]` at them, exactly as in Option A.

### Postgres extensions

If your app relies on extensions like `pg_stat_statements`, enable them through the addon command — no SSH or manual `psql`:

```bash
hop3 addon postgres extensions your-app-db pg_stat_statements
```

Extensions are allow-listed, so only the ones Hop3 ships support for will install.

## Step 5: Deploy to Hop3

Add Hop3 as a Git remote — this is the replacement for App Platform's GitHub auto-deploy:

```bash
git remote add hop3 hop3@your-droplet.example.com:your-app
```

Deploy:

```bash
git push hop3 main
```

Every subsequent `git push hop3 main` redeploys, just like a push to your App Platform-linked branch.

## Step 6: Point Your Domain

App Platform managed your domain and certificate for you. On Hop3 you point DNS at the Droplet yourself. Update your DNS — if your domain is already on DigitalOcean DNS, this is one record:

```
your-app.example.com  A  your-droplet-ip
```

Once Let's Encrypt is configured on the server, Hop3 requests a certificate for the domain at deploy time. Out of the box, a freshly installed server serves a self-signed certificate until you point it at an ACME provider.

## Common Migration Issues

### Workers and background jobs

App Platform `worker` components run continuously alongside your service. In Hop3 they live in the same app under `[run.workers]`:

```toml
[run.workers]
worker = "celery -A myapp worker"
scheduler = "celery -A myapp beat"
```

App Platform `job` components run at a point in the deploy lifecycle. A pre-deploy job (migrations, asset compilation) becomes `before-run`:

```toml
[run]
before-run = ["python manage.py migrate"]
```

### Scheduled tasks

App Platform doesn't have a first-class cron primitive — teams usually run a scheduler as a long-lived worker (the `scheduler` line above) or lean on an external trigger. Both translate directly: keep the scheduler as a `[run.workers]` entry, or use system cron on the Droplet:

```bash
ssh root@your-droplet.example.com
crontab -e
# Add: 0 * * * * /home/hop3/apps/your-app/venv/bin/python /home/hop3/apps/your-app/src/manage.py cleanup
```

### Scaling

App Platform scales by instance count and size, and the Pro tier can autoscale. Hop3 scaling is manual:

```bash
hop3 ps scale your-app web=3 worker=2
```

There is no autoscaler yet — you set the process counts you want. For most single-Droplet workloads this is a feature, not a limitation: fixed counts mean fixed, predictable resource use.

### Preview / branch deploys

App Platform can spin up a deployment per pull request. Hop3 doesn't have managed preview deploys yet. Workarounds:

1. Deploy a staging app manually: `your-app-staging`
2. Use branch-based names: `your-app-feature-x`

### Multiple components, multiple apps

If your spec has several `service` components (a real microservice split, not just web + workers), create one Hop3 app per service and wire them together with env vars. They run on the same Droplet and reach each other over localhost. There's no multi-region or edge placement — Hop3 is a single server — so a spec that fanned components across regions doesn't carry over; everything lands on the one Droplet.

## Command Mapping

| App Platform (`doctl apps`) | Hop3 |
|-----------------------------|------|
| `doctl apps create` | `hop3 app create` |
| `doctl apps list` | `hop3 app list` |
| `doctl apps get <id>` | `hop3 app status --app X` |
| `doctl apps spec get <id>` | (read your `hop3.toml`) |
| `doctl apps update <id> --spec` | edit `hop3.toml`, `git push hop3 main` |
| `doctl apps logs <id> --follow` | `hop3 app logs --app X` |
| `doctl apps create-deployment <id>` | `git push hop3 main` (or `hop3 deploy`) |
| Set component env in spec | `hop3 env set K=V --app X` |
| View component env | `hop3 env show --app X` |
| Restart a deployment | `hop3 app restart --app X` |
| Console / `doctl apps console` | `hop3 app run --app X` |
| Manage app domain | `hop3 domain add <host> --app X` |
| `doctl databases create` | `hop3 addon create <type> <name>` |
| `doctl apps delete <id>` | `hop3 app destroy --app X` |

## Cost and Lock-In

The pitch is narrow and concrete: you're not changing clouds, you're dropping the App Platform premium.

App Platform meters each component and each managed add-on separately. A typical small app — one Basic service, a worker, and a managed database — runs past what a single equivalently sized Droplet costs, and a medium app with multiple instances and a Pro database climbs further. Move the compute onto a Droplet you run with Hop3 and you pay for the Droplet (and, if you keep it, the managed database) — not for each component slot.

| | App Platform | Hop3 on a Droplet |
|-|--------------|-------------------|
| Web service | per-component instance fee | — |
| Worker component | per-component instance fee | — |
| Managed database | managed add-on fee | addon on the Droplet, or keep managed |
| Compute | bundled per-component | one Droplet you already understand |

You keep DigitalOcean's infrastructure: the Droplet, the VPC and private networking, Spaces, DigitalOcean DNS, Droplet backups and snapshots. You drop the per-component billing and the managed-platform layer — and you gain a config file that lives in your repo instead of a spec that lives in DigitalOcean's control plane. The trade-off is the same one as any self-host: you manage the Droplet, but you control everything on it, and the bill stops scaling per component.

## Rollback Plan

App Platform keeps running while you migrate — nothing forces a hard cutover:

1. Deploy to Hop3 on the Droplet with a test domain.
2. If you chose Option A, you're pointing at the same database App Platform uses — verify reads and writes behave.
3. Switch DNS to the Droplet.
4. Keep the App Platform app running for 1-2 weeks.
5. Delete the App Platform app when confident — and, if you migrated the database into an addon, decommission the managed database last.

Because the low-risk path keeps your DigitalOcean Managed Database in place, the riskiest part of the move — the data — can wait until after the compute cutover has proven itself.

## Getting Help

- [Hop3 Documentation](https://hop3.cloud)
- [GitHub Issues](https://github.com/abilian/hop3/issues)
- [Troubleshooting Guide](/guides/troubleshooting/)

---

*Coming from a different platform? The concepts are similar. Check the [Getting Started guide](/get-started/) for a fresh start.*
