# Migrating from Railway to Hop3

Railway makes the first deploy effortless: push a repo, Nixpacks figures out how to build it, click to add a Postgres plugin, and you're live. The friction shows up later, on the invoice. Usage-based billing is wonderful until a traffic spike, a runaway worker, or a forgotten staging service turns a predictable bill into a surprise. If you've reached the point where you'd trade per-second metering for a flat monthly cost you control, Hop3 gives you the same git-push-to-deploy experience on a server you rent at a fixed price. This guide helps you migrate existing Railway apps to Hop3.

## What's Similar

Railway and Hop3 share the same core promise: you hand over source code, the platform detects how to build it, provisions a database, and runs it behind TLS.

| Railway | Hop3 |
|---------|------|
| `railway up` | `git push hop3 main` |
| Nixpacks auto-detection | Native auto-detection (or the Nix builder) |
| Database plugin | `hop3 addon create` |
| Project variables | `[env]` in `hop3.toml` / `hop3 env set` |
| No Procfile needed | No Procfile needed (start command auto-detected) |

Just like Nixpacks infers your start command, Hop3 auto-detects the process model from your project — you don't have to write a `Procfile`. If you want explicit control, you pin it in `hop3.toml` (or add a `Procfile`), but neither is required to get going.

One difference to keep in mind: Railway's CLI and dashboard scope everything to the currently linked project/service. Hop3 uses spaces between words and targets the app with the `--app` flag rather than a positional argument or a linked context. So setting a variable is `hop3 env set FOO=bar --app myapp`.

## What's Different

| Railway | Hop3 |
|---------|------|
| Managed platform | Self-hosted |
| Usage-based billing | Fixed monthly VPS cost |
| Automatic scaling | Manual scaling (`hop3 ps scale`) |
| Postgres / MySQL / Redis / **Mongo** plugins | PostgreSQL, MySQL, Redis, S3/MinIO — and growing |
| Template marketplace | No marketplace (deploy any repo directly) |
| Multi-region deploys | Single server |

Hop3 is simpler, and the cost is predictable: you manage one server instead of a metered cloud account. The one mapping that isn't clean is **MongoDB** — Railway offers a Mongo plugin, and Hop3 doesn't have a managed MongoDB addon. See [Step 4](#step-4-migrate-your-data) for how to handle that.

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

## Step 2: Export Your Railway Configuration

Pull your Railway variables. From the dashboard, copy them from your service's **Variables** tab, or use the Railway CLI:

```bash
railway variables > railway-env.txt
```

Review the file and remove Railway-managed variables — Hop3 sets the equivalents itself when you attach an addon:

- `DATABASE_URL` (will be set by the Hop3 Postgres/MySQL addon)
- `REDIS_URL` (will be set by the Hop3 Redis addon)
- `PORT` (auto-set by Hop3)
- `RAILWAY_*` variables (Railway-internal, no Hop3 equivalent)

Keep your application's own secrets (`SECRET_KEY`, API keys, feature flags) — those carry over unchanged.

## Step 3: Add hop3.toml

Railway leans on Nixpacks plus project variables, with no file in your repo. Hop3 keeps the same zero-config default — push and it auto-detects — but a `hop3.toml` lets you make the configuration explicit and version it alongside your code:

```toml
[metadata]
id = "your-app"

[env]
# Copy your application's own variables from railway-env.txt
SECRET_KEY = "your-secret-key"
LOG_LEVEL = "info"
HOST_NAME = "your-app.example.com"

[[addons]]
type = "postgres"

[run]
before-run = ["python manage.py migrate"]

[healthcheck]
path = "/health/"
```

Railway's project variables become the `[env]` table. The database plugin you clicked in the dashboard becomes a `[[addons]]` entry — declaring it here auto-provisions the addon on first deploy and injects `DATABASE_URL` into the app, so you don't set that yourself.

## Step 4: Migrate Your Data

### Postgres, MySQL, or Redis

For the three relational/cache plugins Railway offers and Hop3 supports, the migration is a dump-and-restore.

First, create the database addon and attach it to your app (or skip this if you declared `[[addons]]` in `hop3.toml`, which provisions it on deploy):

```bash
hop3 addon create postgres your-app-db
hop3 addon attach your-app-db --app your-app
```

Get the connection details:

```bash
hop3 addon show your-app-db
```

Export from Railway. Railway exposes a `DATABASE_URL` for the plugin; use it with the standard tooling:

```bash
# Postgres — dump using Railway's connection string
pg_dump "$RAILWAY_DATABASE_URL" -Fc -f latest.dump
```

Import to Hop3. The `postgres import` verb reads a dump from stdin:

```bash
hop3 addon postgres import your-app-db --confirm=your-app-db < latest.dump
```

(Redis data is usually cache and can start fresh; if you need it, `hop3 addon redis import your-app-db --confirm=your-app-db < dump.rdb`.)

### MongoDB — the gap to name

Hop3 ships PostgreSQL, MySQL, Redis, and S3/MinIO addons — **and no MongoDB**. If your Railway app uses the Mongo plugin, there is no managed Hop3 equivalent to migrate into. You have two practical paths:

1. **Keep an external managed MongoDB** (MongoDB Atlas, or any host you run) and point your app at it. Hop3 doesn't manage it, but it doesn't need to — set the connection string as a plain variable:

   ```bash
   hop3 env set MONGODB_URI="mongodb+srv://user:pass@cluster.example.net/db" --app your-app
   ```

   This is the same trick you'd use to keep any external managed database — Hop3 happily runs an app whose datastore lives elsewhere.

2. **Move the data to a store Hop3 does manage.** If the document model is a fit for it, migrating to Postgres (with `jsonb` columns) lets you fold the database into Hop3's addon lifecycle, backups, and exposure controls. That's a code change, not a config change — weigh it against keeping Atlas.

If a managed MongoDB addon would unblock your migration, that's a platform gap worth telling us about.

## Step 5: Deploy to Hop3

Add Hop3 as a git remote:

```bash
git remote add hop3 hop3@your-server.com:your-app
```

Deploy:

```bash
git push hop3 main
```

This is the direct analog of `railway up`: Hop3 receives the push, detects the language and framework, builds the app, configures the reverse proxy, and starts the process. You can also deploy from a working directory without git using `hop3 deploy`.

## Step 6: Point Your Domain

Update your DNS:

```
your-app.example.com  A  your-server-ip
```

Bind the hostname to the app:

```bash
hop3 domain add your-app.example.com --app your-app
```

Out of the box, a freshly installed server serves a self-signed certificate. Once you point the server at an ACME provider (Let's Encrypt), Hop3 requests a real certificate for the domain at deploy time.

## Common Migration Issues

### Nixpacks vs Toolchains

Railway builds with Nixpacks, which inspects your repo and assembles a build. Hop3 auto-detects the language with native toolchains the same way — Python, Node.js, Go, Ruby, Rust, Java, PHP, Elixir, and .NET are recognized from the files in your repo. Most apps build unchanged.

| Railway (Nixpacks) | Hop3 |
|--------------------|------|
| Python detected | `python` (auto-detected) |
| Node detected | `node` (auto-detected) |
| Go detected | `go` (auto-detected) |
| Custom Nixpacks config | `[build]` section |

For multi-language apps (e.g. a Python backend that builds a JS frontend):

```toml
[build]
toolchain = "python"
before-build = "npm install && npm run build"
```

### Reproducible Builds with the Nix Builder

Nixpacks is itself Nix-based, so if part of why you liked Railway was reproducible builds, Hop3 has a Nix builder that gives you the same property — pinned, reproducible environments — without the Nixpacks abstraction in between:

```toml
[build]
builder = "nix"

[nix]
# template-driven Nix build; no hand-written hop3.nix required
```

If you'd rather build a container, the Docker builder works too:

```toml
[build]
builder = "docker"
```

### Postgres Extensions

If your app needs Postgres extensions (`postgis`, `pgvector`, `pg_stat_statements`), enable them through the addon command — no SSH or manual `psql`:

```bash
hop3 addon postgres extensions your-app-db pgvector
```

Extensions are allow-listed, so only the ones Hop3 ships support for will install.

### Scheduled Jobs and Workers

Railway runs cron and worker services as separate services in the project. In Hop3, declare workers in `hop3.toml`:

```toml
[run.workers]
scheduler = "celery -A myapp beat"
worker = "celery -A myapp worker"
```

Or use system cron on the server for periodic jobs:

```bash
ssh root@your-server.com
crontab -e
# 0 * * * * /home/hop3/apps/your-app/venv/bin/python /home/hop3/apps/your-app/src/manage.py cleanup
```

### Scaling

Railway scales replicas and resources for you. Hop3 scaling is manual and explicit — you set the process count:

```bash
hop3 ps scale your-app web=3 worker=2
```

There's no autoscaling and no multi-region: it's one server, and you size it. For many apps that came to Railway from a hobby tier, a single right-sized VPS is more than enough — and the bill doesn't move when traffic does.

## Command Mapping

| Railway | Hop3 Command |
|---------|--------------|
| `railway init` | `hop3 app create` |
| `railway list` | `hop3 app list` |
| `railway status` | `hop3 app status --app X` |
| `railway variables` | `hop3 env show --app X` |
| `railway variables --set K=V` | `hop3 env set K=V --app X` |
| `railway logs` | `hop3 app logs --app X` |
| `railway up` | `git push hop3 main` |
| `railway run` | `hop3 app run --app X` |
| `railway restart` | `hop3 app restart --app X` |
| `railway add` (database plugin) | `hop3 addon create <type> <name>` + `hop3 addon attach <name> --app X` |
| Plugin connection details | `hop3 addon show <name>` |
| (scale replicas in dashboard) | `hop3 ps scale --app X web=N` |
| (pause service) | `hop3 app stop --app X` |

## Cost and Lock-In

Railway's pricing is usage-based: you pay for the vCPU-seconds and memory your services actually consume, plus egress. That's efficient when usage is low and steady, and it's exactly what bites when it isn't — a busy month, a memory leak, a staging environment someone forgot to delete, and the bill climbs in a way that's hard to forecast.

Hop3's cost is the price of the VPS, full stop. A small app on a $10–20/month server, a medium app on a $30–40/month server — the number doesn't change because you got featured on Hacker News. You trade autoscaling and zero-ops for a flat, predictable line item and full control of the box.

The lock-in angle matters too. Railway's plugins, project model, and dashboard are Railway's. Hop3 runs on a server you own, with your data in addons you can dump, expose, and back up yourself (`hop3 backup create`, `hop3 addon postgres export`). Moving off Hop3 later is `pg_dump` and a tarball, not a support ticket.

What you give up is real and worth naming: no template marketplace, no review apps, no pipelines, no autoscaling, no multi-region. Hop3 is a single server you operate. If those managed conveniences are load-bearing for your team, weigh that against the cost predictability before you switch.

## Rollback Plan

Keep your Railway services running during the migration:

1. Deploy to Hop3 with a test domain (e.g. `your-app-staging.example.com`).
2. Verify the app, the database import, and any workers.
3. Switch DNS to point at the Hop3 server.
4. Keep the Railway services running for 1–2 weeks.
5. Delete the Railway project once you're confident — and watch one last bill close out.

Because the Railway environment stays live until you delete it, the worst case is switching DNS back; nothing about the Hop3 deploy touches your Railway project.

## Getting Help

- [Hop3 Documentation](https://hop3.cloud)
- [GitHub Issues](https://github.com/abilian/hop3/issues)

---

*Coming from a different platform? The concepts are similar. Check the [Getting Started guide](/get-started/) for a fresh start.*
