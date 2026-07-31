# Migrating from Docker Compose to Hop3

You already self-host. You have a VPS, a `compose.yaml` with a web service plus a Postgres or Redis next to it, and `docker compose up -d` brings the whole thing online. It works — but you are also the platform. You hand-wrote the nginx reverse proxy in front of the web container, you renew TLS with a certbot cron, you `git pull && docker compose build && docker compose up -d` to deploy, and you restart containers by hand when something wedges. Compose orchestrates the containers; everything around them is yours to maintain. Hop3 gives you that managed layer — git-push deploys, managed database/cache addons, generated nginx, automatic ACME — on the same single box you already rent. This guide helps you migrate a single-host Compose stack to Hop3.

## What's Similar

Both Hop3 and Docker Compose describe a deployment declaratively in a file in your repo, and both run several cooperating pieces (a web app, a database, a cache) on one host.

| Docker Compose | Hop3 |
|----------------|------|
| `compose.yaml` | `hop3.toml` |
| `docker compose up -d` / rebuild | `git push hop3 main` |
| `environment:` on a service | `[env]` |
| A `postgres` / `redis` service | `hop3 addon create` |
| `volumes:` for persistent data | `[[volumes]]` |
| `docker compose logs -f` | `hop3 app logs --app X` |

The shape carries over: your web service becomes a Hop3 *app*, and the backing services you currently run as your own containers become Hop3 *addons*. The app you target in CLI commands is always the `--app` flag, never a positional argument: `hop3 env set FOO=bar --app myapp`.

One workflow difference to keep in mind: with Compose you deploy by rebuilding and recreating containers on the box (often after a `git pull`). With Hop3 you deploy by pushing to its remote — `git push hop3 main` — and the platform builds, configures the proxy, and restarts the processes for you.

## What's Different

| Docker Compose | Hop3 |
|----------------|------|
| You run the orchestrator | Managed platform on your server |
| You write nginx + certbot by hand | Hop3 generates nginx and handles ACME |
| Every service is a container you maintain | One app model + managed addons |
| `deploy.replicas` (Swarm) | Manual scaling (`hop3 ps scale`) |
| Arbitrary service graph | One app per web service; databases/caches are addons |

Compose is a general container orchestrator: it will run anything you put in the file, but it does nothing above the container line. Hop3 is opinionated — it knows what a web app, a database, and a cache are — so it can manage the proxy, TLS, addons, and deploys for you, in exchange for fitting your stack into that model.

## Mapping Compose Services to Hop3

A single-host `compose.yaml` is usually a small graph: one or two application services plus some backing infrastructure. Each piece maps onto a Hop3 concept.

| Compose service | Hop3 equivalent |
|-----------------|-----------------|
| The `web` / app service (your code) | A Hop3 app |
| Its `build:` / Dockerfile | `[build] builder = "docker"` (or drop it for a native toolchain) |
| A `worker` service running your code | A `[run.workers]` entry on the same app |
| A `postgres` / `mysql` / `redis` service | `hop3 addon create postgres\|mysql\|redis …` |
| `environment:` | `[env]` |
| `volumes:` (named volume for app data) | `[[volumes]]` |
| `ports:` (HTTP) | Hop3 binds `$PORT` behind nginx — you declare nothing |
| `ports:` (non-HTTP, e.g. SMTP/RTMP) | `[[ports]]` |
| `depends_on:` / service-to-service URLs | Addon attachment injects the connection URL |
| The `nginx` service + certbot | Removed — Hop3 generates nginx and handles ACME |

The big structural change: in Compose, your database and cache are containers *you* run, reachable over the Compose network by service name (`postgres://db:5432/...`). In Hop3 they are managed addons. You stop running them yourself; you create them with `hop3 addon create`, attach them, and Hop3 injects the connection URL (`DATABASE_URL`, `REDIS_URL`, …) into the app's environment. Likewise, the hand-rolled `nginx` service and certbot drop out entirely — Hop3 owns the reverse proxy and the certificate.

Be clear-eyed about the boundary: a Compose file with a handful of bespoke long-running services (a search engine, a message broker, a sidecar you wrote) does not collapse into one app and a couple of addons. Hop3's addons are PostgreSQL, MySQL, Redis, and S3/MinIO (and growing) — not an arbitrary container catalog. A stack like that becomes one app plus addons for what Hop3 supports, plus *additional Hop3 apps* for the other long-running pieces (each its own app, bound or not bound to a domain). A dozen custom services is a more involved translation, done by hand — see the note at the end of this section.

## Step 1: Set Up Your Hop3 Server

You may be able to reuse the box you already run Compose on, but the cleanest path is a fresh server so the migration doesn't fight your existing nginx/certbot. Provision a server (Ubuntu 24.04 LTS recommended; Debian, Fedora, and Rocky/Alma also work) and install Hop3:

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

## Step 2: Export Your Compose Configuration

Your configuration lives in `compose.yaml` and any `.env` file it reads. Collect the environment your app actually needs, then drop the variables Hop3 manages for you:

- `DATABASE_URL` (will be set by the Hop3 Postgres addon)
- `REDIS_URL` (will be set by the Hop3 Redis addon)
- `PORT` (auto-set by Hop3 — your app should bind `$PORT`)
- Any host/port pointing at a Compose service name (e.g. `DB_HOST=db`, `REDIS_HOST=cache`) — the addon connection URL replaces these

What's left — your `SECRET_KEY`, third-party API keys, feature flags — becomes your `[env]` block in the next step.

## Step 3: Translate compose.yaml to hop3.toml

Here is a representative single-host stack: a Python web app built from a Dockerfile, a background worker running the same image, a Postgres database, a Redis cache, a named volume for uploads, and a hand-rolled nginx + certbot in front.

```yaml
# compose.yaml
services:
  web:
    build: .
    environment:
      DJANGO_SETTINGS_MODULE: myapp.settings.production
      SECRET_KEY: ${SECRET_KEY}
      DATABASE_URL: postgres://myapp:secret@db:5432/myapp
      REDIS_URL: redis://cache:6379/0
    volumes:
      - uploads:/app/uploads
    depends_on:
      - db
      - cache
    # no ports: — nginx is the only thing exposed publicly

  worker:
    build: .
    command: celery -A myapp worker
    environment:
      DATABASE_URL: postgres://myapp:secret@db:5432/myapp
      REDIS_URL: redis://cache:6379/0
    depends_on:
      - db
      - cache

  db:
    image: postgres:16
    environment:
      POSTGRES_USER: myapp
      POSTGRES_PASSWORD: secret
      POSTGRES_DB: myapp
    volumes:
      - pgdata:/var/lib/postgresql/data

  cache:
    image: redis:7

  nginx:
    image: nginx
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/conf.d/default.conf
      - ./certs:/etc/nginx/certs
    depends_on:
      - web
  # + a certbot container or cron renewing ./certs
```

The equivalent `hop3.toml` keeps the `web` and `worker` services (they run *your* code) and drops everything else — the `db`, `cache`, and `nginx` services all become platform concerns:

```toml
[metadata]
id = "myapp"

[build]
builder = "docker"

[env]
# Variables from your compose environment / .env, minus the ones Hop3 injects
DJANGO_SETTINGS_MODULE = "myapp.settings.production"
SECRET_KEY = "your-secret-key"

[run]
before-run = ["python manage.py migrate"]

[run.workers]
worker = "celery -A myapp worker"

[[volumes]]
name = "uploads"
target = "uploads"

[healthcheck]
path = "/health/"
```

A few translation notes:

- **The Dockerfile stays, or goes.** `build: .` becomes `[build] builder = "docker"` — Hop3 builds your existing Dockerfile on the server. If your Dockerfile is a stock single-stage build of a standard runtime (Python, Node, Go, …), you can often *delete it* and let Hop3's native toolchain auto-detect the language from `requirements.txt` / `package.json` / `go.mod`. Native builds skip the container layer entirely; the Docker builder is the safe choice when your build is bespoke.
- **The `worker` service folds into the app.** Because it runs the same image with a different command, it becomes a `[run.workers]` entry on the one app, sharing its code and environment — you no longer run it as a separate service.
- **`db` and `cache` disappear from the file.** You stop running Postgres and Redis as your own containers. They become addons you create in Step 4; Hop3 injects `DATABASE_URL` and `REDIS_URL`, which is why you removed them from `[env]`.
- **The `volumes:` entry becomes `[[volumes]]`.** The named `uploads` volume — the data that must survive a redeploy — is declared with `[[volumes]]`. (The `pgdata` volume is gone with the `db` service; the Postgres addon manages its own storage.)
- **No `ports:` for the web app.** Your app should bind `$PORT`; Hop3 assigns it and routes HTTP/HTTPS by hostname through nginx. You declare nothing. `[[ports]]` exists only for non-HTTP services that bind a fixed host port directly (SMTP, RTMP, Matrix federation), and exactly one app may own such a port.
- **The `nginx` and certbot services are deleted.** Hop3 generates the nginx configuration and handles the certificate — that whole slice of your Compose file is now the platform's job (see Step 6 and Step 7).

If you have a Procfile-style process list already, Hop3 can bootstrap a `hop3.toml` from it:

```bash
cd myapp/
hop3 app migrate procfile .
```

That is the only config importer Hop3 ships — it converts a `Procfile` to a `hop3.toml`. There is no automated importer for `compose.yaml`; the translation above is done by hand, which is also your chance to drop the proxy/TLS/database boilerplate that Compose made you carry.

## Step 4: Migrate Your Data

In Compose, your database is a container writing to a named volume (`pgdata`). In Hop3 it's a managed addon. Move the data with the standard tools.

### Create the addons

```bash
hop3 addon create postgres myapp-db
hop3 addon attach myapp-db --app myapp

hop3 addon create redis myapp-cache
hop3 addon attach myapp-cache --app myapp
```

Get the connection details:

```bash
hop3 addon show myapp-db
```

Once attached, Hop3 injects `DATABASE_URL` and `REDIS_URL` into the app automatically — that's why you removed them from `[env]` in Step 3.

### Export from your Compose Postgres

Dump straight out of the running container:

```bash
docker compose exec -T db pg_dump -U myapp -Fc myapp > latest.dump
```

### Import to Hop3

```bash
# Copy dump to the Hop3 server
scp latest.dump root@your-server.com:/tmp/

# SSH to the server and import
ssh root@your-server.com
sudo -u postgres pg_restore --verbose --no-owner \
    -d myapp_db /tmp/latest.dump
```

### Postgres extensions

If your Compose Postgres image had extensions enabled (`pg_stat_statements`, `pgcrypto`, …), enable them through the addon command — no SSH or manual `psql` needed:

```bash
hop3 addon postgres extensions myapp-db pg_stat_statements
```

Extensions are allow-listed, so only the ones Hop3 ships support for will install.

### Redis

Most Compose Redis containers hold cache data, so starting fresh is usually fine — the addon injects `REDIS_URL` and your app repopulates the cache on its own. If you persisted Redis and need the data, dump and restore it explicitly.

### Keeping an external managed database (optional)

If you'd rather not move the data yet — or you were already pointing Compose at a managed database elsewhere — you can keep that database and just point Hop3 at it: set its connection string under `[env]` (e.g. `DATABASE_URL = "postgresql://…"`) instead of creating an addon. You lose Hop3's backup integration for that database, but it's a clean way to migrate the app first and the data later.

## Step 5: Replacing depends_on and the Compose network

In Compose, services find each other by name over the Compose network (`db`, `cache`), and `depends_on` controls start order. Hop3 has neither, and you don't need them:

- **Service discovery** is replaced by addon attachment. Instead of `postgres://db:5432/myapp`, your app reads the `DATABASE_URL` that the attached addon injects. Hostnames like `db` and `cache` no longer exist — drop any `DB_HOST=db` style variables.
- **`depends_on`** is replaced by the platform managing addon lifecycle. The Postgres and Redis addons are running services on the host; the app connects to them via the injected URL. There is no ordering to declare.

So the entire `depends_on` graph and the Compose-network hostnames collapse into "attach the addon, read its URL."

## Step 6: Deploy to Hop3

Add Hop3 as a remote and push:

```bash
git remote add hop3 hop3@your-server.com:myapp
git push hop3 main
```

You can also deploy from a working directory with `hop3 deploy`. The deploy uploads your source, builds it (your Dockerfile via the Docker builder, or a native toolchain), configures the reverse proxy, and starts the web process and any workers — the equivalent of `docker compose build && docker compose up -d`, but the proxy and TLS come for free.

This is where the hand-maintained pieces of your Compose stack disappear: there is no nginx service to template, no certbot cron to babysit, and no `docker compose up` to run on the box.

## Step 7: Reverse Proxy, TLS, and Domains

This is the part of your Compose stack that Hop3 most clearly replaces. You can delete the `nginx` service, its `nginx.conf`, and the certbot container/cron — Hop3 owns all of it.

Bind your hostnames to the app declaratively in `hop3.toml`:

```toml
[domains]
list = ["myapp.example.com", "www.myapp.example.com"]
```

Then point DNS at the server:

```
myapp.example.com  A  your-server-ip
```

Out of the box, a freshly installed server serves a self-signed certificate. Once Let's Encrypt / ACME is configured on the server, Hop3 requests a real certificate for the domain at deploy time — replacing your certbot renewal entirely.

## Command Mapping

| Docker Compose | Hop3 |
|----------------|------|
| `docker compose ps` | `hop3 app list` |
| `docker compose up -d` (first run) | `hop3 app create` + `git push hop3 main` |
| `docker compose up -d --build` (deploy) | `git push hop3 main` |
| Inspect a service | `hop3 app status --app X` |
| Edit `environment:` + recreate | `hop3 env set K=V --app X` |
| `printenv` inside a container | `hop3 env show --app X` |
| `docker compose logs -f` | `hop3 app logs --app X` |
| `docker compose ps` (replica count) | `hop3 ps --app X` |
| `deploy.replicas` (Swarm) | `hop3 ps scale --app X web=N` |
| `docker compose restart web` | `hop3 app restart --app X` |
| `docker compose exec web <cmd>` | `hop3 app run --app X` |
| A `postgres` / `redis` service | `hop3 addon list` / `hop3 addon show <name>` |
| `docker compose stop` | `hop3 app stop --app X` |

## Cost and Lock-in

Compose is free, and you're already on one box — so the move isn't about a lower bill. It's about what you stop maintaining. Today, on that same VPS, you own the nginx config, the TLS renewal, the rebuild-and-recreate deploy step, the container restarts when something wedges, and the database container and its volume. Hop3 runs on the same single server at the same fixed VPS price, and hands those back to the platform: deploys are a git push, the proxy and certificate are generated, and the database and cache are managed addons with built-in backups.

On lock-in, both directions are clean. There's no proprietary control plane to escape: your app stays a normal repo, your data is a standard Postgres/Redis you can `pg_dump` out at any time, and a `hop3.toml` runs anywhere Hop3 runs. You're trading a pile of hand-maintained ops glue for a managed layer — without trading away ownership of the server or the data.

## Where Hop3 Falls Short of Docker Compose

Compose is a general orchestrator; Hop3 is an opinionated PaaS. Be clear about the gaps before you switch:

- **Arbitrary services.** Compose runs any container you write. Hop3's managed addons are PostgreSQL, MySQL, Redis, and S3/MinIO (and growing) — not an open container catalog. A stack with several bespoke long-running services (a custom search engine, a message broker, a sidecar) doesn't fully collapse: each non-app service becomes either a supported addon, an additional Hop3 app, or — if Hop3 can't express it — a piece you keep running yourself. A dozen custom services is a genuinely involved translation, not a one-to-one port.
- **No automated importer.** There is no `compose.yaml` → `hop3.toml` converter. The only config importer Hop3 ships is `hop3 app migrate procfile <dir>` for Procfiles. The Compose translation is done by hand (which is also where you shed the proxy/TLS/db boilerplate).
- **Scaling is manual.** Compose/Swarm `deploy.replicas` has no autoscaling equivalent — Hop3 scaling is `hop3 ps scale --app myapp web=3 worker=2`. You set the counts; the platform doesn't change them for you.
- **Single server.** No multi-host, no Swarm cluster, no multi-region. Hop3 runs your apps on one server you provision.
- **No review apps / pipelines.** There's no per-pull-request environment. The workaround is a manually deployed staging app (`myapp-staging`, or a per-branch `myapp-feature-x`).
- **MFA.** Multi-factor auth on the Hop3 control plane is deferred.

If your Compose file is mostly "web app + database + cache + nginx", the fit is excellent and you delete more than you add. If it's a sprawling multi-service graph that leans on Compose as a general orchestrator, weigh the translation cost first.

## Rollback Plan

Keep your Compose stack running during the migration — ideally on its current box, with Hop3 on a fresh server, so the two don't fight over ports 80/443:

1. Deploy to Hop3 with a test domain.
2. Verify the app, its workers, and its background jobs all run against the migrated database.
3. Switch DNS to the Hop3 server.
4. Keep the Compose stack (and its database volume) running for 1–2 weeks.
5. `docker compose down` and decommission the old stack once you're confident.

Because Hop3 deploys on an explicit `git push hop3` rather than on a container rebuild, you can keep both stacks live and only cut over when the Hop3 deployment has proven itself.

## Getting Help

- [Hop3 Documentation](https://hop3.cloud)
- [GitHub Issues](https://github.com/abilian/hop3/issues)
- [Troubleshooting Guide](/guides/troubleshooting/)

---

*Coming from a different platform? The concepts are similar. Check the [Getting Started guide](/get-started/) for a fresh start.*
