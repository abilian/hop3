# Migrating from CapRover to Hop3

CapRover gave you a self-hosted PaaS with a web dashboard, one-click databases, and `caprover deploy`. The thing it also gave you, whether you wanted it or not, is Docker Swarm: an orchestrator you have to keep healthy, almost always for a single node that never needed a cluster in the first place. If you're tired of maintaining Swarm to run one box, Hop3 offers the same deploy-and-forget feeling on a plain single-server model — and your apps don't even need a Dockerfile. This guide helps you migrate existing CapRover apps to Hop3.

## What's Similar

Both are self-hosted PaaS layers that sit between "raw VPS" and "managed cloud," so the day-to-day shape is familiar:

| CapRover | Hop3 |
|----------|------|
| `caprover deploy` | `git push hop3 main` |
| `captain-definition` + Dockerfile | `hop3.toml` (+ optional `Dockerfile`) |
| One-click database apps | `hop3 addon create postgres\|mysql\|redis` |
| Dashboard env vars | `[env]` in `hop3.toml` |
| Persistent directories | `[[volumes]]` |
| Custom domains + auto-HTTPS | `hop3 domain add` + ACME |

You still push code and get a running app behind HTTPS on your own server. The difference is what runs underneath it.

One thing worth internalizing early: CapRover is dashboard-first, and Hop3 is config-and-CLI-first. Where you used to click through the captain panel, you'll edit a `hop3.toml` checked into your repo and run space-separated CLI commands. The app you're targeting is always the `--app` flag, never a positional argument. So "set a variable on app `myapp` in the dashboard" becomes `hop3 env set FOO=bar --app myapp`.

## What's Different

| CapRover | Hop3 |
|----------|------|
| Docker Swarm under the hood | Plain single-server, no Swarm |
| Everything is a container | Native toolchains *or* Docker builder |
| One-click app marketplace | PostgreSQL, MySQL, Redis, S3/MinIO — and growing |
| Richer web dashboard | Config-in-repo + CLI/TUI |
| Cluster-capable (multi-node) | Single server |

The headline is the orchestrator. CapRover runs your apps as Swarm services, which means a Swarm manager, an overlay network, and a scheduler you're on the hook to keep alive — overhead you pay even when there's exactly one node. Hop3 drops Swarm entirely. Apps run as ordinary processes managed by uWSGI behind nginx, and if an app genuinely wants to be a container, you opt into the Docker builder for that one app. You get to keep "it's just Docker" for the apps that need it, without making every app pay the Swarm tax.

Be clear-eyed about the trade: CapRover's one-click marketplace and dashboard are more featureful than what Hop3 ships today. Hop3 gives you four first-class addons (Postgres, MySQL, Redis, S3/MinIO) and a CLI/TUI rather than a point-and-click catalog. And scaling is manual — there's no autoscaler.

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

Unlike CapRover, there's no Swarm to initialize, no leader to elect, and no overlay network to wire up. The installer sets up nginx, uWSGI, and the Hop3 server, and you're ready to deploy.

## Step 2: Read Your CapRover App Definition

Open each app in the CapRover dashboard and collect three things before you touch Hop3:

1. **The `captain-definition`** in your repo — it either points at a `Dockerfile` (or an inline `dockerfileLines`) or at a prebuilt image.
2. **The environment variables** from the app's *App Configs* tab.
3. **The persistent directories** from the app's *Persistent Directories* setting (the host paths CapRover bind-mounts into the container).

You're going to translate each of those into a `hop3.toml`. There is no automatic importer for `captain-definition` — Hop3's only config importer is for Procfiles (`hop3 app migrate procfile <dir>`), so the `captain-definition` mapping below is done by hand. It's mechanical, and you only do it once per app.

## Step 3: Decide — Native Toolchain or Docker Builder

This is the one real decision in the migration, and CapRover never gave you the choice: everything was a container.

**Option A — drop the Dockerfile, go native.** If your `captain-definition` Dockerfile is the standard "install a runtime, copy code, install deps, run a server" recipe, Hop3 can almost certainly build it natively with no Dockerfile at all. Native toolchains auto-detect Python, Node.js, Go, Ruby, Rust, Java, PHP, Elixir, and .NET from the files in your repo. This is the lighter, faster path — no image builds, no registry.

**Option B — keep the Dockerfile, use the Docker builder.** If your Dockerfile does something genuinely custom (system packages, a compiled C extension, a multi-stage build you trust), keep it and tell Hop3 to use it:

```toml
[build]
builder = "docker"
```

Hop3 will `docker build` from your `Dockerfile` and run the result. You keep the container; you just lose the Swarm wrapped around it.

A good rule: start with Option A. If the build fails on a missing system dependency, fall back to Option B for that one app.

## Step 4: Translate captain-definition to hop3.toml

Here's a representative `captain-definition` and the Dockerfile it points at:

```json
{
  "schemaVersion": 2,
  "dockerfilePath": "./Dockerfile"
}
```

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
RUN python manage.py collectstatic --noinput
CMD gunicorn myapp.wsgi --bind 0.0.0.0:$PORT
```

In CapRover you'd also have set environment variables and a persistent directory through the dashboard. The native Hop3 equivalent of all of that is a single `hop3.toml`:

```toml
[metadata]
id = "myapp"

[build]
toolchain = "python"
before-build = "pip install -r requirements.txt"

[run]
before-run = ["python manage.py collectstatic --noinput", "python manage.py migrate"]

[env]
# Copy these from CapRover's App Configs tab.
SECRET_KEY = "your-secret-key"
DJANGO_SETTINGS_MODULE = "myapp.settings.production"

[[volumes]]
name = "uploads"
target = "data/uploads"

[domains]
list = ["myapp.example.com"]

[healthcheck]
path = "/health/"
```

A few notes on the mapping:

- **The `CMD`/server command** doesn't need to be transcribed by hand if you keep a `Procfile` — Hop3 reads it for the process model. A `web: gunicorn myapp.wsgi` line is enough. (`$PORT` is auto-assigned by Hop3; don't hardcode a port.)
- **`RUN` steps** split between build-time and run-time. Dependency installs and asset compilation that should happen during the build go in `[build] before-build`; migrations and anything that must run against the live database go in `[run] before-run`.
- **CapRover persistent directories** become `[[volumes]]`. Each `target` is a directory inside your app tree that survives redeploys (each deploy wipes and re-extracts `src/`, so anything you need to keep lives in a volume).
- **The container itself** disappears in the native path. If you chose Option B instead, you'd drop the `[build] toolchain` line, set `builder = "docker"`, and keep your `Dockerfile` — the `[env]`, `[[volumes]]`, `[domains]`, and `[healthcheck]` sections stay exactly the same.

If your app already ships a `Procfile`, you can generate a starting `hop3.toml` from it:

```bash
cd myapp/
hop3 app migrate procfile . --dry-run   # preview
hop3 app migrate procfile .             # write hop3.toml
```

Then add the `[env]`, `[[volumes]]`, and `[domains]` sections by hand from your CapRover dashboard.

## Step 5: Migrate Your Databases

In CapRover, your database was a one-click app — a Postgres/MySQL/Redis container with a persistent directory. In Hop3, it's a first-class addon with managed credentials, dump/restore verbs, and backup integration.

### Create and attach the addon

```bash
hop3 addon create postgres myapp-db
hop3 addon attach myapp-db --app myapp
```

Attaching injects the connection variables (`DATABASE_URL`, …) into the app's environment automatically — you don't copy a connection string around by hand the way you did between CapRover apps.

### Move the data

Dump from your CapRover Postgres container, then load it into the Hop3 addon. From the CapRover host:

```bash
# Find the postgres service container and dump it
docker exec $(docker ps -qf name=srv-captain--postgres) \
    pg_dump -U postgres -Fc mydb > latest.dump
```

Get the Hop3 addon's connection details and import:

```bash
hop3 addon show myapp-db

# Copy dump to the Hop3 server and restore
scp latest.dump root@your-server.com:/tmp/
ssh root@your-server.com
sudo -u postgres pg_restore --verbose --no-owner \
    -d myapp_db /tmp/latest.dump
```

MySQL and Redis follow the same shape (`mysqldump` / `BGSAVE` on the CapRover side, `hop3 addon create mysql|redis` plus the type-specific restore verbs on the Hop3 side).

### Postgres extensions

If your CapRover Postgres relied on an extension like `pg_stat_statements`, enable it through the addon command — no SSH or manual `psql`:

```bash
hop3 addon postgres extensions myapp-db pg_stat_statements
```

Extensions are allow-listed, so only the ones Hop3 ships support for will install.

### Keeping an external managed database

If a CapRover app already pointed at a managed database outside the cluster (RDS, a managed Postgres, etc.), you don't have to move it at all. Skip the addon and point `[env]` at the existing URL:

```toml
[env]
DATABASE_URL = "postgresql://user:pass@db.example.com:5432/mydb"
```

### A note on addon coverage

CapRover's marketplace offers one-click containers for a long tail of services. Hop3 ships four addons — PostgreSQL, MySQL, Redis, and S3/MinIO. If a CapRover app depended on something outside that set (a message broker, a document store), you have two routes: run it as its own Docker-builder Hop3 app, or point at an external/managed instance via `[env]`. There's no MongoDB addon and no managed queue today.

## Step 6: Deploy to Hop3

Add Hop3 as a git remote and push — this is the `caprover deploy` equivalent:

```bash
git remote add hop3 hop3@your-server.com:myapp
git push hop3 main
```

Hop3 builds the app (natively or via your Dockerfile, per Step 3), configures nginx, and starts it. You'll see build output stream as it happens.

## Step 7: Point Your Domain and Get HTTPS

CapRover handled custom domains and auto-HTTPS from the dashboard. In Hop3, you bind hostnames with the CLI (or the `[domains]` section you already added in Step 4) and update DNS:

```bash
hop3 domain add myapp.example.com --app myapp
```

```
myapp.example.com  A  your-server-ip
```

Out of the box, a freshly installed server serves a self-signed certificate. Once Let's Encrypt/ACME is configured on the server, Hop3 requests a real certificate for the domain at deploy time — the same automatic-HTTPS outcome CapRover gave you, just configured server-side rather than per-app in a dashboard.

## Common Migration Issues

### Scheduled jobs

CapRover doesn't have a built-in scheduler; people usually run a cron-like worker container. In Hop3, declare a worker process:

```toml
[run.workers]
scheduler = "celery -A myapp beat"
```

Or use system cron on the server for one-off maintenance tasks.

### Scaling

CapRover lets you set the replica count of a Swarm service. Hop3 scales the same way conceptually, but manually and without an autoscaler:

```bash
hop3 ps scale myapp web=3 worker=2
```

There's no automatic scaling — you set the process counts you want.

### The Docker registry

CapRover builds images and pushes them to a registry (its own or an external one) so Swarm nodes can pull them. With Hop3's native path there's no image and no registry at all. With the Docker builder, the image is built and run on the same single server — still no registry to operate.

### Multi-node clusters

If you were genuinely using CapRover across several Swarm nodes, that's the one capability Hop3 doesn't replace: Hop3 is a single-server model. There's no multi-node clustering, no multi-region, and no edge. If you need a cluster, Hop3 isn't the destination. If — like most CapRover installs — you were running one node and maintaining Swarm anyway, that's exactly the overhead Hop3 removes.

## Command and Concept Mapping

| CapRover | Hop3 |
|----------|------|
| Dashboard: create app | `hop3 app create` |
| Dashboard: app list | `hop3 app list` |
| Dashboard: app details | `hop3 app status --app X` |
| Dashboard: app configs (env) | `hop3 env show --app X` |
| Dashboard: set env var | `hop3 env set K=V --app X` |
| Dashboard: app logs | `hop3 app logs --app X` |
| Swarm service replicas | `hop3 ps --app X` / `hop3 ps scale --app X web=N` |
| Dashboard: restart app | `hop3 app restart --app X` |
| `docker exec` into the service | `hop3 app run --app X` |
| One-click database app | `hop3 addon create <type> <name>` |
| Database connection (manual) | `hop3 addon attach <name> --app X` |
| One-click app details | `hop3 addon show <name>` |
| Custom domain + auto-HTTPS | `hop3 domain add <host> --app X` |
| `captain-definition` + Dockerfile | `[build] builder = "docker"` (or native) |
| Persistent directories | `[[volumes]]` |
| `caprover deploy` | `git push hop3 main` |

## Lock-in and Cost Angle

Neither CapRover nor Hop3 charges you a platform fee — both are open-source and run on a VPS you already pay for, so this isn't a pricing comparison. The real axis is operational overhead and lock-in.

**Operational overhead.** With CapRover, part of what you maintain is Swarm itself: the manager, the overlay network, the registry, and the failure modes that come with an orchestrator. For a single node, that's complexity with no payoff. Hop3 removes the orchestrator layer; you maintain one server running ordinary processes behind nginx.

**Lock-in.** CapRover's unit of truth is the `captain-definition` plus dashboard state; Hop3's is a `hop3.toml` checked into your repo, and for the apps you keep on the Docker builder, your existing `Dockerfile`. Your data leaves through standard `pg_dump`/`mysqldump`/RDB dumps in both directions. Migrating *out* of either is a matter of moving images or dumps — there's no proprietary data format holding you.

The trade-off is the one this whole post circles: you give up CapRover's richer dashboard and one-click marketplace, and in return you stop running an orchestrator to manage a single box.

## Rollback Plan

Keep your CapRover app running during the migration:

1. Deploy to Hop3 with a test domain (e.g. `myapp-hop3.example.com`).
2. Verify the app and its data — hit real endpoints, check the database restored correctly.
3. Switch DNS to the Hop3 server.
4. Keep the CapRover app running for 1–2 weeks as a fallback.
5. Tear down the CapRover app — and, if it was your only one, the Swarm node — once you're confident.

Because your CapRover stack is untouched until step 3, the rollback at any point before then is just "don't switch DNS."

## Getting Help

- [Hop3 Documentation](https://hop3.cloud)
- [GitHub Issues](https://github.com/abilian/hop3/issues)
- [Troubleshooting Guide](/guides/troubleshooting/)

---

*Coming from a different platform? The concepts are similar. Check the [Getting Started guide](/get-started/) for a fresh start.*
