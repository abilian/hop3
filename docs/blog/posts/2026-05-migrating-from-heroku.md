---
date: 2026-05-29
template: blog_post.html
description: Guide for migrating existing Heroku applications to Hop3.
tags:
  - Tutorial
  - Migration
---

# Migrating from Heroku to Hop3

!!! note "There is a maintained version of this guide"

    This post is kept as published. The version that tracks the current CLI
    lives in the documentation: **[Migrating from Heroku](/guides/migration/from-heroku/)**,
    alongside guides for twenty other platforms under
    [Migrating to Hop3](/guides/migration-guide/).

Thinking about leaving Heroku? Whether it's cost predictability, provider independence, or data residency requirements, Hop3 offers a familiar deployment experience on your own infrastructure. This guide helps you migrate existing Heroku apps to Hop3.

## What's Similar

Hop3 was designed with Heroku workflows in mind:

| Heroku | Hop3 |
|--------|------|
| `git push heroku main` | `git push hop3 main` |
| `Procfile` | `Procfile` (compatible) |
| `heroku config:set` | `hop3 env set` |
| `heroku addons:create` | `hop3 addon create` |
| `heroku logs -t` | `hop3 logs` |

Your `Procfile` works unchanged. Your deployment workflow stays the same.

One syntactic difference to keep in mind: where Heroku uses a colon (`config:set`), Hop3 uses spaces (`hop3 env set`), and the app you're targeting is always the `--app` flag rather than a positional argument. So `heroku config:set FOO=bar -a myapp` becomes `hop3 env set FOO=bar --app myapp`.

## What's Different

| Heroku | Hop3 |
|--------|------|
| Managed platform | Self-hosted |
| Automatic scaling | Manual scaling |
| Many addon types | PostgreSQL, MySQL, Redis, S3/MinIO — and growing |
| Review apps | Not yet supported |
| Pipelines | Not yet supported |

Hop3 is simpler. You manage one server instead of a complex cloud setup.

## Step 1: Set Up Your Hop3 Server

Provision a server (Ubuntu 24.04 LTS recommended) and install Hop3:

```bash
ssh root@your-server.com
curl -LsSf https://hop3.cloud/install-server.py | sudo python3 -
```

Install the CLI on your local machine:

```bash
hop3-install cli
```

Log into your server (this stores its token and makes it the default target):

```bash
hop3 login --ssh root@your-server.com
```

## Step 2: Export Your Heroku Configuration

Get your Heroku environment variables:

```bash
heroku config -a your-app --shell > heroku-env.txt
```

Review the file and remove Heroku-specific variables:
- `DATABASE_URL` (will be set by Hop3 addon)
- `REDIS_URL` (will be set by Hop3 addon)
- `PORT` (auto-set by Hop3)
- `HEROKU_*` variables

## Step 3: Add hop3.toml

While `Procfile` is compatible, `hop3.toml` gives you more control:

```toml
[metadata]
id = "your-app"

[env]
# Copy environment variables from heroku-env.txt
SECRET_KEY = "your-secret-key"
DJANGO_SETTINGS_MODULE = "myapp.settings.production"
HOST_NAME = "your-app.example.com"

[run]
before-run = ["python manage.py migrate"]

[healthcheck]
path = "/health/"
```

## Step 4: Migrate Your Database

### Export from Heroku

```bash
heroku pg:backups:capture -a your-app
heroku pg:backups:download -a your-app
```

This creates `latest.dump`.

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

## Step 6: Point Your Domain

Update your DNS:

```
your-app.example.com  A  your-server-ip
```

Once Let's Encrypt is configured on the server, Hop3 requests a certificate for the domain at deploy time. Out of the box, a freshly installed server serves a self-signed certificate until you point it at an ACME provider.

## Common Migration Issues

### Buildpacks vs Toolchains

Heroku uses buildpacks; Hop3 uses toolchains. Most apps work unchanged, but some differences:

| Heroku Buildpack | Hop3 Toolchain |
|------------------|----------------|
| `heroku/python` | `python` (auto-detected) |
| `heroku/nodejs` | `node` (auto-detected) |
| `heroku/ruby` | `ruby` (auto-detected) |
| Multi-buildpack | Use `[build]` section |

For multi-language apps (e.g., Python + Node for assets):

```toml
[build]
toolchain = "python"
before-build = "npm install && npm run build"
```

### Runtime Versions

Heroku uses `runtime.txt` for Python version. Hop3 uses the system Python (3.11-3.13 depending on OS).

For specific versions, you can set up pyenv or use Docker builder:

```toml
[build]
builder = "docker"
```

### Heroku Postgres Extensions

If you use Heroku-specific Postgres extensions (like `pg_stat_statements`), enable them through the addon command — no SSH or manual `psql` needed:

```bash
hop3 addon postgres extensions your-app-db pg_stat_statements
```

Extensions are allow-listed, so only the ones Hop3 ships support for will install.

### Heroku Redis

Migrate your Redis data if needed:

```bash
# Export from Heroku (if using persistence)
heroku redis:cli -a your-app
> BGSAVE

# Or just start fresh - most Redis data is cache
```

### Scheduled Jobs

Heroku Scheduler doesn't exist in Hop3. Use cron workers:

```toml
[run.workers]
scheduler = "celery -A myapp beat"
```

Or use system cron:

```bash
ssh root@your-server.com
crontab -e
# Add: 0 * * * * /home/hop3/apps/your-app/venv/bin/python /home/hop3/apps/your-app/src/manage.py cleanup
```

### Review Apps

Hop3 doesn't have review apps yet. Workarounds:

1. Deploy staging apps manually: `your-app-staging`
2. Use branch-based names: `your-app-feature-x`

## Command Mapping

| Heroku Command | Hop3 Command |
|----------------|--------------|
| `heroku create` | `hop3 app create` |
| `heroku apps` | `hop3 app list` |
| `heroku apps:info` | `hop3 app status --app X` |
| `heroku config` | `hop3 env show --app X` |
| `heroku config:set` | `hop3 env set K=V --app X` |
| `heroku logs -t` | `hop3 logs --app X` |
| `heroku ps` | `hop3 ps --app X` |
| `heroku ps:scale` | `hop3 ps scale --app X web=N` |
| `heroku restart` | `hop3 app restart --app X` |
| `heroku run` | `hop3 run --app X` |
| `heroku addons` | `hop3 addon list` |
| `heroku pg:info` | `hop3 addon show <name>` |
| `heroku maintenance:on` | `hop3 app stop --app X` |

## Cost Comparison

| | Heroku | Hop3 (self-hosted) |
|-|--------|-------------------|
| Basic dyno | $7/month | - |
| Standard dyno | $25/month | - |
| Postgres (hobby) | $9/month | - |
| Postgres (standard) | $50/month | - |
| **Total (small app)** | ~$60/month | ~$10/month (VPS) |
| **Total (medium app)** | ~$150/month | ~$30/month (VPS) |

The trade-off: you manage the server, but you control everything.

## Rollback Plan

Keep your Heroku app running during migration:

1. Deploy to Hop3 with a test domain
2. Verify everything works
3. Switch DNS to Hop3
4. Keep Heroku app running for 1-2 weeks
5. Delete Heroku app when confident

## Getting Help

- [Hop3 Documentation](https://hop3.cloud)
- [GitHub Issues](https://github.com/abilian/hop3/issues)
- [Troubleshooting Guide](/guides/troubleshooting/)

---

*Coming from a different platform? The concepts are similar. Check the [Getting Started guide](/get-started/) for a fresh start.*
