# Migrating from Piku to Hop3

If you run [Piku](https://github.com/piku/piku), you already know the best part of Hop3 by heart: you `git push`, and your app is live behind nginx. Hop3 grew out of that same lineage — a tiny git-push PaaS on nginx and uWSGI, no Docker or Kubernetes required. So this is the easiest migration in the series: the mental model barely changes. What changes is what sits around it. You keep `git push` and your `Procfile`, and you gain managed addons (Postgres, MySQL, Redis, S3), more language toolchains, a proper CLI and dashboard, healthchecks, and a declarative `hop3.toml`. This guide helps you move an existing Piku app to Hop3.

## What's Similar

Hop3 shares Piku's core ideas, so most of your habits carry over:

| Piku | Hop3 |
|------|------|
| `git push piku master` | `git push hop3 main` |
| `Procfile` | `Procfile` (unchanged) |
| `piku config:set` | `hop3 env set` |
| `piku scale web=2` | `hop3 ps scale --app X web=2` |
| `piku run` | `hop3 app run --app X` |
| `piku logs` | `hop3 app logs --app X` |

Your `Procfile` works unchanged, and the runtime model is the one you already trust: each web process binds to `$PORT` and Hop3 puts nginx in front of uWSGI for you. The difference is that Hop3 wires that nginx + uWSGI plumbing automatically, instead of you tuning `ENV` knobs like `NGINX_*` and `UWSGI_*` by hand.

One syntactic difference to keep in mind: where Piku uses a colon (`config:set`) and a positional app inferred from the directory, Hop3 uses spaces (`hop3 env set`) and the app you're targeting is always the `--app` flag. So `piku config:set FOO=bar` (run from the app's checkout) becomes `hop3 env set FOO=bar --app myapp`.

## What's Different

| Piku | Hop3 |
|------|------|
| Single-file, dependency-light | Larger system (server + CLI + TUI) |
| `ENV` file for config | `[env]` in `hop3.toml` (or `hop3 env set`) |
| No managed databases (install them yourself) | PostgreSQL, MySQL, Redis, S3/MinIO — and growing |
| `piku` over SSH only | CLI, terminal dashboard (TUI), JSON-RPC API |
| No declarative healthchecks | `[healthcheck]` in `hop3.toml` |

This is genuinely a trade. Piku is smaller and leaner — that is its whole point, and if a single Python file on a tiny VPS is all you want, Piku is a fine place to stay. Hop3 is a bigger system because it does more: it manages backing services as first-class addons, ships a real CLI and a dashboard, and runs healthchecks. The thing you'd move *for* is usually the database. On Piku you install and babysit Postgres or Redis yourself; on Hop3 they're addons you create and attach.

Hop3 is still single-server like Piku. There's no multi-region, no cluster, no edge, no review apps, no pipelines, and scaling is manual (you choose the process counts, nothing autoscales). If you're happy on one box, that's the same box you've always had.

## Step 1: Set Up Your Hop3 Server

Provision a server (Ubuntu 24.04 LTS or later recommended; Debian, Fedora, and Rocky/Alma also work) and install Hop3:

```bash
ssh root@your-server.com
curl -LsSf https://hop3.cloud/install-server.py | sudo python3 -
```

This can be the same box you run Piku on, or a fresh one — running both side by side during the move is the safe path (see Rollback below).

Install the CLI on your local machine:

```bash
hop3-install cli
```

Connect the CLI to your server. On a first install this also creates the
admin account and stores your API token:

```bash
hop3 init --ssh root@your-server.com
```

## Step 2: Translate Your Piku ENV File

Piku keeps per-app config in an `ENV` file in the app's repo. Hop3 keeps it in `[env]` inside `hop3.toml` (or you set it with `hop3 env set`). Open your Piku `ENV` and split it into two buckets:

- **Your app's own settings** (`SECRET_KEY`, `DJANGO_SETTINGS_MODULE`, feature flags, …) move into `[env]` verbatim.
- **Piku plumbing variables** can be dropped — Hop3 manages them for you:
  - `NGINX_*`, `UWSGI_*` — Hop3 configures nginx and uWSGI itself.
  - `PORT` — auto-assigned by Hop3 (your app still reads `$PORT`).
  - `SERVER_NAME` — becomes the `[domains]` section (see below).
  - `DATABASE_URL` / `REDIS_URL` — if you used self-installed databases, these are replaced by addon-injected values in Step 4.

## Step 3: Add hop3.toml

While your `Procfile` works as-is, `hop3.toml` is where Hop3 earns its keep — config, addons, and healthchecks become declarative and live in the repo. Here's a representative Python/Flask app translated from a Piku `ENV` + `Procfile`:

A typical Piku app looks like this:

```
# Procfile
web: gunicorn app:app

# ENV
SERVER_NAME=myapp.example.com
NGINX_SERVER_NAME=myapp.example.com
SECRET_KEY=s3cret
LOG_LEVEL=info
```

The equivalent `hop3.toml`:

```toml
[metadata]
id = "myapp"

[env]
SECRET_KEY = "s3cret"
LOG_LEVEL = "info"

[domains]
list = ["myapp.example.com"]

[run]
before-run = ["python manage.py migrate"]

[healthcheck]
path = "/health/"
```

You can keep the `Procfile` for the process model (`web: gunicorn app:app`) and let `hop3.toml` carry config — they coexist. If you'd rather not retype the `Procfile`, Hop3 can read it and scaffold a `hop3.toml` for you:

```bash
cd myapp/
hop3 app migrate procfile .
```

This is the only built-in config importer: it translates a `Procfile` into a starter `hop3.toml`. There's no importer for other formats — the `ENV` → `[env]` and `SERVER_NAME` → `[domains]` mapping above is done by hand, which is short work for a Piku app.

## Step 4: Migrate Your Data (the main upgrade)

This is the step that makes the move worth it. On Piku you installed Postgres or Redis yourself and pointed `DATABASE_URL` at it. On Hop3 these are addons: Hop3 provisions them, stores the credentials, and injects the connection variables for you.

### Postgres

Dump your existing database (the one you installed alongside Piku):

```bash
ssh root@your-piku-server.com
sudo -u postgres pg_dump -Fc myapp > /tmp/myapp.dump
```

Create the addon and attach it to your app:

```bash
hop3 addon create postgres myapp-db
hop3 addon attach myapp-db --app myapp
```

Attaching injects `DATABASE_URL` into the app's environment — you no longer maintain it by hand. Check the connection details:

```bash
hop3 addon show myapp-db
```

Import the dump:

```bash
# Copy dump to the Hop3 server
scp /tmp/myapp.dump root@your-server.com:/tmp/

# SSH to the Hop3 server and restore
ssh root@your-server.com
sudo -u postgres pg_restore --verbose --no-owner \
    -d myapp_db /tmp/myapp.dump
```

If your app relies on a Postgres extension (like `pg_stat_statements`), enable it through the addon command — no manual `psql` needed:

```bash
hop3 addon postgres extensions myapp-db pg_stat_statements
```

Extensions are allow-listed, so only the ones Hop3 ships support for will install.

### Redis

```bash
hop3 addon create redis myapp-cache
hop3 addon attach myapp-cache --app myapp
```

This injects `REDIS_URL`. Most Redis data is cache, so starting fresh is usually fine; if you need to carry data over, copy your `dump.rdb` from the old box. MySQL and S3/MinIO work the same way (`hop3 addon create mysql …`, `hop3 addon create s3 …`).

### Keeping an external managed database

If you already pay for a managed database elsewhere and want to keep it, skip the addon and just point `[env]` at its URL:

```toml
[env]
DATABASE_URL = "postgresql://user:pass@managed-host:5432/myapp"
```

Note the available addon types are PostgreSQL, MySQL, Redis, and S3/MinIO (and growing). If you ran something else next to Piku — MongoDB, a message queue — there's no first-class addon for it yet; run it externally and point `[env]` at it.

## Step 5: Deploy to Hop3

The part you already know. Add Hop3 as a git remote and push:

```bash
git remote add hop3 hop3@your-server.com:myapp
git push hop3 main
```

(Piku pushes the `master` branch by convention; Hop3 examples use `main` — push whichever branch you deploy.) If you'd rather not set up a remote, `hop3 deploy` uploads the current directory directly.

After the push you can drive the app exactly as you did with Piku, just with the verb mapping:

```bash
hop3 app status --app myapp
hop3 app logs --app myapp
hop3 ps scale --app myapp web=2
hop3 app run --app myapp python manage.py migrate
```

## Step 6: Point Your Domain

Update your DNS to the Hop3 server:

```
myapp.example.com  A  your-server-ip
```

You set the hostname declaratively in `hop3.toml` (`[domains]`, above) or with the CLI:

```bash
hop3 domain add myapp.example.com --app myapp
```

On Piku, TLS was something you arranged yourself (often via an `acme.sh` integration). Hop3 serves a self-signed certificate out of the box, and once you point the server at an ACME provider (Let's Encrypt), it requests a real certificate for the domain at deploy time.

## Scheduled Jobs

Piku has no built-in scheduler — you used system cron, and you still can. For app-aware periodic work, declare a worker in `hop3.toml`:

```toml
[run.workers]
scheduler = "celery -A myapp beat"
```

Or keep using system cron on the server for one-off scripts.

## Command Mapping

| Piku Command | Hop3 Command |
|--------------|--------------|
| `git push piku master` | `git push hop3 main` |
| `piku apps` | `hop3 app list` |
| `piku config` | `hop3 env show --app X` |
| `piku config:set K=V` | `hop3 env set K=V --app X` |
| `piku config:get K` | `hop3 env show --app X` |
| `piku config:live` | `hop3 env show --app X` |
| `piku logs` | `hop3 app logs --app X` |
| `piku ps` | `hop3 ps --app X` |
| `piku scale web=N` | `hop3 ps scale --app X web=N` |
| `piku run <cmd>` | `hop3 app run --app X <cmd>` |
| `piku restart` | `hop3 app restart --app X` |
| `piku stop` | `hop3 app stop --app X` |
| `piku destroy` | `hop3 app destroy --app X` |
| (install your own DB) | `hop3 addon create postgres <name>` |

## Lock-in and What You're Really Buying

Neither Piku nor Hop3 locks you in: both are open source, both deploy to a plain Linux server you control, and both keep the `git push` workflow that means your repo is the source of truth. Moving between them is config translation, not a rewrite — and moving *off* either one is the same `git push` to wherever you go next.

So the question isn't lock-in, it's operational surface. With Piku you own the database lifecycle, the TLS plumbing, and the nginx/uWSGI knobs. With Hop3 those become managed: addons, ACME at deploy time, automatic proxy config, healthchecks, and a CLI/dashboard to see it all. You pay for that with a larger system to run. If your app is a single process with no database, Piku's leanness is hard to beat. The moment you're hand-managing Postgres next to Piku, Hop3's addons are the upgrade you came for.

## Rollback Plan

Because both are git-push PaaSes on the same kind of box, you can run them in parallel and cut over only when ready:

1. Stand up Hop3 (a new server, or alongside Piku) and `git push hop3 main`.
2. Verify the app on a test hostname, with its data restored and addons attached.
3. Switch DNS to the Hop3 server.
4. Keep the Piku app running for a week or two as a fallback.
5. Decommission the Piku deployment once you're confident.

Your `Procfile` and your code are untouched throughout, so backing out is just pointing DNS back at Piku.

## Getting Help

- [Hop3 Documentation](https://hop3.cloud)
- [GitHub Issues](https://github.com/abilian/hop3/issues)

---

*Coming from a different platform? The concepts are similar. Check the [Getting Started guide](/get-started/) for a fresh start.*
