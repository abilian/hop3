# Migrating from Scalingo to Hop3

Scalingo is a solid, EU-hosted, Heroku-style PaaS, and if you're on it you already have data residency sorted. So this isn't a sovereignty pitch — it's a cost-and-control one. The case for moving is simple: you stop paying per-dyno and per-addon margins, and you own the box end to end. Hop3 keeps the workflow you already know — `git push`, a `Procfile`, buildpack-style auto-detection, addons, one-off run containers — but runs it on a server you control. This guide helps you migrate an existing Scalingo app to Hop3.

The trade is just as plain, and we'll keep it in front of you: Scalingo runs the platform for you and ships a broader addon catalogue. On Hop3 you take on the ops, and a couple of addon types (MongoDB, Elasticsearch, InfluxDB) have no Hop3-native equivalent yet — those stay external. More on that below.

## What's Similar

Hop3 was designed around the same Heroku-style workflow Scalingo uses:

| Scalingo | Hop3 |
|----------|------|
| `git push scalingo master` | `git push hop3 main` |
| `Procfile` | `Procfile` (compatible) |
| `scalingo env-set` | `hop3 env set` |
| `scalingo addons-add` | `hop3 addon create` |
| `scalingo logs -f` | `hop3 app logs` |

Your `Procfile` works unchanged. Your deployment workflow stays the same: commit, push, and the platform builds and runs your app.

One syntactic difference to keep in mind: where Scalingo passes the app with `-a` (and uses a verb-noun form like `env-set`), Hop3 uses spaces and the app you're targeting is always the `--app` flag rather than a positional argument. So `scalingo --app myapp env-set FOO=bar` becomes `hop3 env set FOO=bar --app myapp`.

## What's Different

| Scalingo | Hop3 |
|----------|------|
| Managed platform | Self-hosted |
| Automatic + manual scaling | Manual scaling (`hop3 ps scale`) |
| Broad addon catalogue | PostgreSQL, MySQL, Redis, S3/MinIO — and growing |
| Review apps | Not yet supported |
| Multi-region regions (osc-fr1, osc-secnum-fr1) | Single server |

Hop3 is simpler. You manage one server instead of a managed fleet — which is the point if you want full control, and the cost if you wanted someone else to carry the pager.

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

## Step 2: Export Your Scalingo Configuration

Get your Scalingo environment variables:

```bash
scalingo --app your-app env > scalingo-env.txt
```

Review the file and remove Scalingo-managed variables — these are re-provided by Hop3 addons or set automatically:
- `DATABASE_URL` / `SCALINGO_POSTGRESQL_URL` (will be set by the Hop3 Postgres addon)
- `REDIS_URL` / `SCALINGO_REDIS_URL` (will be set by the Hop3 Redis addon)
- `PORT` (auto-set by Hop3)
- Other `SCALINGO_*` variables

Keep your real application secrets (`SECRET_KEY`, API keys, settings module, and so on) — those carry over unchanged.

## Step 3: Add hop3.toml

While `Procfile` is compatible, `hop3.toml` gives you more control. If you only have a `Procfile` today, you can generate a starting point from it:

```bash
hop3 app migrate procfile .
```

Then fill in the rest. A representative `hop3.toml` translated from a Scalingo app:

```toml
[metadata]
id = "your-app"

[env]
# Copy your real secrets from scalingo-env.txt (drop the SCALINGO_* ones)
SECRET_KEY = "your-secret-key"
DJANGO_SETTINGS_MODULE = "myapp.settings.production"
HOST_NAME = "your-app.example.com"

[run]
before-run = ["python manage.py migrate"]

[healthcheck]
path = "/health/"
```

There is no importer for `scalingo.json` or for a Scalingo "manifest" — Hop3 only imports a `Procfile`. The mapping is direct, so you do the rest by hand: env vars go under `[env]`, your `web:` and `worker:` process lines stay in the `Procfile` (or move to `[run.workers]`), and any release-phase command becomes `before-run`.

## Step 4: Migrate Your Database

### Export from Scalingo

Scalingo databases are reachable over an SSH tunnel and dumped with the standard Postgres tools. Open a tunnel to your addon, then dump:

```bash
scalingo --app your-app db-tunnel SCALINGO_POSTGRESQL_URL
# In another terminal, with the tunnel open:
pg_dump -Fc -h 127.0.0.1 -p 10000 -U your_user your_db > latest.dump
```

(Use the host, port, user, and database name printed by `db-tunnel`.)

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

## Step 5: Deploy to Hop3

Add Hop3 as a remote:

```bash
git remote add hop3 hop3@your-server.com:your-app
```

Deploy:

```bash
git push hop3 main
```

(Scalingo deploys off `master` by convention; Hop3's remote tracks `main`. If your branch is still `master`, push `master:main` or rename the branch.)

## Step 6: Point Your Domain

Update your DNS:

```
your-app.example.com  A  your-server-ip
```

Once Let's Encrypt is configured on the server, Hop3 requests a certificate for the domain at deploy time. Out of the box, a freshly installed server serves a self-signed certificate until you point it at an ACME provider. (On Scalingo, TLS was automatic; here it's one configuration step you own.)

## Common Migration Issues

### Buildpacks vs Toolchains

Scalingo uses buildpacks; Hop3 uses toolchains with the same auto-detection. Most apps build unchanged:

| Scalingo Buildpack | Hop3 Toolchain |
|--------------------|----------------|
| Python | `python` (auto-detected) |
| Node.js | `node` (auto-detected) |
| Ruby | `ruby` (auto-detected) |
| Go | `go` (auto-detected) |
| Multi-buildpack | Use `[build]` section |

For multi-language apps (e.g., Python + Node for assets):

```toml
[build]
toolchain = "python"
before-build = "npm install && npm run build"
```

If a buildpack did something Hop3's native toolchains don't, you can drop down to the Docker builder and build from your own Dockerfile:

```toml
[build]
builder = "docker"
```

### Runtime Versions

Scalingo pins versions in files like `.python-version`, `package.json` `engines`, or a Ruby `.ruby-version`. Hop3's native toolchains use the system runtime (e.g. Python 3.11–3.13 depending on OS). For a specific version, use the Docker builder (above) or the Nix builder, which pins the toolchain reproducibly.

### Postgres Extensions

If your Scalingo Postgres used extensions (like `pg_stat_statements`), enable them through the addon command — no SSH or manual `psql` needed:

```bash
hop3 addon postgres extensions your-app-db pg_stat_statements
```

Extensions are allow-listed, so only the ones Hop3 ships support for will install.

### Redis

Migrate your Redis data if needed:

```bash
# Most Redis use is cache - usually you can just start fresh.
# If you need the data, dump from Scalingo (via db-tunnel + redis-cli)
# and load it into the Hop3 addon.
hop3 addon create redis your-app-cache
hop3 addon attach your-app-cache --app your-app
```

### MongoDB, Elasticsearch, InfluxDB

This is the gap to plan around. Scalingo offers MongoDB, Elasticsearch, and InfluxDB addons; Hop3 does not have native equivalents — its addon set is PostgreSQL, MySQL, Redis, and S3/MinIO (and growing). If your app depends on one of these, you have two options:

1. Keep using a managed instance (Scalingo's, or any provider's) and point `[env]` at its connection URL:

   ```toml
   [env]
   MONGODB_URL = "mongodb://user:pass@managed-host:27017/db"
   ```

2. Run the service yourself on the same box (outside Hop3's addon management) and connect to it over localhost — you own that operational surface.

Neither is as turnkey as a Scalingo addon. Weigh it before you commit a Mongo/ES/Influx-heavy app.

### Scheduled Jobs

Scalingo has a cron-like scheduler and clock-process patterns. On Hop3, use a worker process for an in-app scheduler:

```toml
[run.workers]
scheduler = "celery -A myapp beat"
```

Or use system cron on the server:

```bash
ssh root@your-server.com
crontab -e
# Add: 0 * * * * /home/hop3/apps/your-app/venv/bin/python /home/hop3/apps/your-app/src/manage.py cleanup
```

### Review Apps

Scalingo has review apps (one ephemeral app per pull request). Hop3 doesn't have an equivalent yet. Workarounds:

1. Deploy staging apps manually: `your-app-staging`
2. Use branch-based names: `your-app-feature-x`

This is real work Scalingo did for you, so factor it into the decision if review apps are central to your team's flow.

## Command Mapping

| Scalingo Command | Hop3 Command |
|------------------|--------------|
| `scalingo create` | `hop3 app create` |
| `scalingo apps` | `hop3 app list` |
| `scalingo --app X apps-info` | `hop3 app status --app X` |
| `scalingo --app X env` | `hop3 env show --app X` |
| `scalingo --app X env-set K=V` | `hop3 env set K=V --app X` |
| `scalingo --app X logs -f` | `hop3 app logs --app X` |
| `scalingo --app X ps` | `hop3 ps --app X` |
| `scalingo --app X scale web:2` | `hop3 ps scale --app X web=2` |
| `scalingo --app X restart` | `hop3 app restart --app X` |
| `scalingo --app X run <cmd>` | `hop3 app run --app X` |
| `scalingo --app X addons` | `hop3 addon list` |
| `scalingo --app X addons-add postgresql` | `hop3 addon create postgres … && hop3 addon attach …` |
| `scalingo --app X domains-add` | `hop3 domain add <host> --app X` |

## Cost and Lock-in

Scalingo is fairly priced for what it is — a managed EU PaaS — and the math here isn't "Scalingo is expensive". It's that you're paying for management you may not need, on margins you can reclaim by running the box yourself.

| | Scalingo (managed) | Hop3 (self-hosted) |
|-|--------------------|--------------------|
| App container(s) | per-container, per-size | — |
| Postgres addon | per-plan monthly | — |
| Redis addon | per-plan monthly | — |
| **Total (small app)** | a managed-plan bill | ~€10/month (VPS) |
| **Total (medium app)** | a larger managed bill | ~€30/month (VPS) |

The deeper win is lock-in: with Hop3 there's no platform-specific config to keep you in place. `hop3.toml` and a `Procfile` are portable, your data lives in a standard Postgres/MySQL/Redis you can dump and move, and the server is just a Linux box. The cost is the obvious one — you carry the ops Scalingo handled.

## Rollback Plan

Keep your Scalingo app running during migration:

1. Deploy to Hop3 with a test domain
2. Verify everything works (run your suite, click through the app)
3. Switch DNS to Hop3
4. Keep the Scalingo app running for 1-2 weeks
5. Stop and delete the Scalingo app when confident

Because nothing on Hop3 is platform-specific, the reverse is just as easy: if you decide to go back, your `Procfile` still works on Scalingo and your database dump still restores there.

## Getting Help

- [Hop3 Documentation](https://hop3.cloud)
- [GitHub Issues](https://github.com/abilian/hop3/issues)
- [Troubleshooting Guide](/guides/troubleshooting/)

---

*Coming from a different platform? The concepts are similar. Check the [Getting Started guide](/get-started/) for a fresh start.*
