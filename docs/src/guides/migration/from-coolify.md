# Migrating from Coolify to Hop3

If you run Coolify, you already self-host: git-based deploys, a polished web UI, databases and services you provision with a click, all on a server you control. Hop3 shares that goal (keep your apps on your own infrastructure) but takes a different stance on *how* an app runs. Coolify containerises everything: every application, every database, every service is a Docker container it builds and orchestrates for you. Hop3 runs apps natively on the host by default, with Docker as an opt-in builder. This guide walks an existing Coolify app over to Hop3, primitive by primitive.

So why move at all? The usual reasons. You want fewer moving parts: no container layer between your app and the host unless you ask for one. You want your configuration in a declarative `hop3.toml` checked into your repo. You want a lighter footprint on a small VPS, where running every database in a container adds memory and management overhead. Or you want Hop3's deployment model: `git push`, native multi-language toolchains, a reverse-proxy you can choose. Whatever the reason, the concepts map cleanly. The main shift is mental, from "everything is a container" to "the app runs on the host, Docker is one builder among several."

## What's Similar

Coolify and Hop3 share the same skeleton, so most of what you know transfers:

| Coolify | Hop3 |
|---------|------|
| Git-based deploy (push or webhook) | `git push hop3 main` |
| Nixpacks / Dockerfile build | Native toolchains, Docker builder, or Nix builder |
| Managed Postgres / MySQL / Redis | `hop3 addon create` + `hop3 addon attach` |
| Per-resource environment variables | `[env]` in `hop3.toml` / `hop3 env set` |
| Persistent storage volumes | `[[volumes]]` in `hop3.toml` |
| Domains + automatic Let's Encrypt | `hop3 domain add` + Hop3 ACME |

A Coolify *application* becomes a Hop3 *app*; a Coolify managed *database* becomes a Hop3 *addon*. The deployment workflow stays the same: commit, push, watch the build stream by.

Learn the CLI's shape early: Hop3 separates words with spaces and always takes the target app as the `--app` flag. So setting an environment variable is `hop3 env set FOO=bar --app myapp`. If you mostly drove Coolify from the web UI, you'll be doing more from the command line, where every action has a scriptable command.

## What's Different

| Coolify | Hop3 |
|---------|------|
| Everything runs as a Docker container | Apps run natively on the host (Docker optional) |
| Rich web UI, one-click service catalogue | CLI-first, declarative `hop3.toml` |
| Broad catalogue of managed services | PostgreSQL, MySQL, Redis, S3 (Garage), and growing |
| docker-compose stacks | One app plus addons (or several apps) |
| Manual scaling | Manual scaling |
| Single server (or a few, via the UI) | Single server |

Three things change conceptually:

**Native by default, Docker by choice.** This is the headline difference. Coolify always builds a container (with Nixpacks if you have no Dockerfile, with your Dockerfile if you do) and runs it under Docker. Hop3 auto-detects your language and builds with a native toolchain (Python, Node.js, Go, Ruby, Rust, Java, PHP, Elixir, .NET), running the app directly on the host with no container layer. That's lighter and has fewer moving parts. If you want to keep your Dockerfile, Hop3 has a Docker builder (`[build] builder = "docker"`). For fully reproducible builds, there's a Nix builder. So you keep the option you had and no longer pay for it by default.

**Declarative config in the repo.** In Coolify, an app's configuration lives in the dashboard: env vars, the domain, the persistent volume, the build settings are all state you set through the web interface. In Hop3 the same facts live in a `hop3.toml` checked into your repo. The server reads it on deploy. Your configuration becomes reviewable and diffable. Redeploying to a fresh server reproduces the app with no clicking through a UI.

**A smaller, sharper addon set.** Coolify's strength is breadth: a one-click catalogue of databases and services. Hop3 ships four data addons: PostgreSQL, MySQL, Redis, and S3 (Garage). The set is growing. If your app depends on something outside that set, you keep running it as an external service and point an env var at it (see [Data and Addon Migration](#step-4-migrate-your-data-and-addons) below). Coolify has the broader catalogue and the richer UI. Hop3 trades that breadth for a lighter, native-by-default runtime.

## Step 1: Set Up Your Hop3 Server

You already self-host, so this part is quick. Provision a server (Ubuntu 24.04 LTS or later recommended; Debian, Fedora, and Rocky/Alma also work) and install Hop3:

```bash
ssh root@your-server.com
curl -LsSf https://hop3.cloud/install-server.py | sudo python3 -
```

Install the CLI on your local machine:

```bash
uv tool install hop3
```

Connect the CLI to your server. On a first install this also creates the admin account and stores your API token:

```bash
hop3 login root@your-server.com
```

Once your project has a `hop3.toml`, bind its checkout to this server, once, from the project directory: `hop3 context use default`. Until then, `hop3` refuses the commands you run there.

Install Hop3 on a fresh server, away from the box running Coolify. Coolify owns the Docker daemon and the reverse proxy on its host; standing Hop3 up alongside it invites contention over ports 80/443. A clean server lets you migrate at your own pace and cut over with DNS when you're ready.

## Step 2: Export Your Coolify Configuration

Pull the environment variables out of your Coolify application. In the dashboard, each application has an **Environment Variables** tab. Copy them out (Coolify can show or export the list). Save them somewhere you can edit, then drop the ones Hop3 manages for you:

- `DATABASE_URL`: set by the Hop3 Postgres (or MySQL) addon
- `REDIS_URL`: set by the Hop3 Redis addon
- `PORT`: auto-set by Hop3. Your app binds to `$PORT`, the same convention Coolify uses
- Any Coolify-injected variables specific to its container networking

While you're there, note the app's **persistent storage** mounts and **domains**. You'll re-declare both in `hop3.toml`.

## Step 3: Add hop3.toml

This is the heart of the migration: turning the configuration you set through Coolify's UI into one declarative file. Suppose your Coolify application was a Python web app with these settings:

- Build pack: Nixpacks (auto-detected Python)
- Env vars: `SECRET_KEY`, `DJANGO_SETTINGS_MODULE`
- Persistent storage: a volume mounted at `/app/media`
- Database: a managed Postgres
- Domain: `your-app.example.com`

The equivalent `hop3.toml` gathers all of that into one place:

```toml
[metadata]
id = "your-app"

[build]
toolchain = "python"

[env]
# Copy the variables you kept from Coolify's Environment Variables tab
SECRET_KEY = "your-secret-key"
DJANGO_SETTINGS_MODULE = "myapp.settings.production"

[run]
before-run = ["python manage.py migrate"]

[[addons]]
type = "postgres"

[[volumes]]
name = "media"
target = "media"

[domains]
list = ["your-app.example.com"]

[healthcheck]
path = "/health/"
```

The translation follows a few rules:

- **Build pack → toolchain.** Coolify's Nixpacks auto-detection becomes Hop3's native auto-detection. You usually don't need to name the toolchain, because Hop3 detects Python, Node, Go, and the rest from the files in your repo. The explicit `toolchain = "python"` above is just for clarity. If your Coolify app used a Dockerfile, set `builder = "docker"` instead (see [Build Pack vs Toolchain](#build-pack-vs-toolchain) below).
- **Persistent storage → `[[volumes]]`.** Coolify mounts a Docker volume at a path inside the container. Hop3's `[[volumes]]` declares a directory that persists across redeploys (each deploy replaces your source tree, so anything written outside a volume is lost). The `target` is relative to your app's source root; Hop3 stores the data outside the source tree and links it back on every deploy.
- **`before-run`** replaces the post-deploy command you'd configure in Coolify: migrations, asset builds, and the like.
- **`[[addons]]`** declares the database your app needs; attaching it (next step) injects `DATABASE_URL`, the same variable Coolify's managed database gave you.
- **`[domains]`** is the declarative form of the domain you set in Coolify's UI. You can still add domains imperatively later with `hop3 domain add`.

If your repo already has a `Procfile` (some Coolify apps keep one), Hop3 can scaffold a starting `hop3.toml` from it:

```bash
cd your-app/
hop3 app migrate procfile . --dry-run
```

This importer reads a `Procfile` only. No importer exists for Coolify's configuration, a `docker-compose.yml`, or any other format. You translate the rest by hand, as with any move between platforms whose config models differ. The result is a single, reviewable file.

### Translating a docker-compose stack

Coolify supports deploying a `docker-compose.yml` as a single resource: one app plus its databases and side services, all defined in one compose file. Hop3 neither imports nor runs compose files. A multi-service stack decomposes into **one Hop3 app plus addons**, or **several Hop3 apps**, depending on what the services are.

Take a representative compose file:

```yaml
services:
  web:
    build: .
    environment:
      DATABASE_URL: postgres://user:pass@db:5432/app
      REDIS_URL: redis://cache:6379
    ports:
      - "8000:8000"
    volumes:
      - media:/app/media
  db:
    image: postgres:16
    volumes:
      - pgdata:/var/lib/postgresql/data
  cache:
    image: redis:7
volumes:
  media:
  pgdata:
```

The mapping is mechanical once you separate *your code* from *backing services*:

| Compose service | Becomes in Hop3 |
|-----------------|-----------------|
| `web` (your build) | The Hop3 app: its `hop3.toml` |
| `db` (`postgres:16` image) | A Postgres addon: `hop3 addon create postgres your-app-db` |
| `cache` (`redis:7` image) | A Redis addon: `hop3 addon create redis your-app-cache` |
| `media:` volume | `[[volumes]]` in the app's `hop3.toml` |
| `pgdata:` volume | Managed by the addon; you don't declare it |
| `DATABASE_URL` / `REDIS_URL` | Injected by the attached addons, so don't set them yourself |
| `ports: "8000:8000"` | Dropped: Hop3 assigns `$PORT` and proxies by hostname |

The stack collapses to one app (the `web` service's `hop3.toml`, as in Step 3), a Postgres addon, and a Redis addon. The database and cache services in your compose file become Hop3 addons. The connection URLs the addons inject replace the ones you hardcoded.

If a compose service is genuinely a *second application* you wrote (an API and a separate frontend, say), make it a second Hop3 app and wire the two together with env vars.

## Step 4: Migrate Your Data and Addons

### PostgreSQL

In Coolify your database ran as a Postgres container it managed for you. In Hop3 you create the addon and attach it:

```bash
hop3 addon create postgres your-app-db
hop3 addon attach your-app-db --app your-app
```

Get the connection details:

```bash
hop3 addon show your-app-db
```

Now move your data. Dump from the Coolify-managed Postgres container and import on the Hop3 side. Coolify lets you open a terminal into the database container (or you can `docker exec` on its host):

```bash
# On the Coolify host: dump the database from its container
docker exec <coolify-db-container> pg_dump -U postgres -Fc your_app > your-app.dump

# Turn the dump into SQL and load it into the addon (where the hop3 CLI runs)
pg_restore --no-owner --no-acl -f your-app.sql your-app.dump
hop3 addon postgres import your-app-db --confirm=your-app-db < your-app.sql
```

If your app used Postgres extensions (for example `pg_stat_statements` or `pgcrypto`), enable them through the addon command, without opening a `psql` session:

```bash
hop3 addon postgres extensions your-app-db pg_stat_statements
```

Extensions are allow-listed, so only the ones Hop3 ships support for will install.

### MySQL

If your Coolify app used MySQL, the shape is identical. Create a MySQL addon and attach it:

```bash
hop3 addon create mysql your-app-db
hop3 addon attach your-app-db --app your-app
```

Dump from the Coolify MySQL container with `mysqldump`, copy the file over, and import it on the Hop3 server.

### Redis

If your Coolify app used a Redis container, create and attach a Redis addon the same way:

```bash
hop3 addon create redis your-app-cache
hop3 addon attach your-app-cache --app your-app
```

Most Redis data is cache and can start fresh. If you do need to move it, export from the Coolify redis container and reload it on the new server. For the common case, attaching a fresh Redis addon and letting it warm up is simpler.

### Object storage

If your app used S3-compatible object storage (Coolify can run MinIO as a service), Hop3 has an S3 (Garage) addon:

```bash
hop3 addon create s3 your-app-storage
hop3 addon attach your-app-storage --app your-app
```

### Services Hop3 doesn't ship

This is where Coolify's broader catalogue shows. If your app depends on a service outside Hop3's four data addons (MongoDB, RabbitMQ, Elasticsearch, ClickHouse and so on), Hop3 won't provision it for you. The pragmatic path is to keep running that service (on its own box, as a managed offering, or even as a standalone container) and point an env var at it:

```bash
hop3 env set --app your-app MONGODB_URL=mongodb://user:pass@db.internal:27017/yourapp
```

Your app connects to it exactly as it did under Coolify, while Hop3 leaves the service's lifecycle alone. The same approach keeps an existing external managed database during a phased migration: point `[env]` at its URL.

## Step 5: Deploy to Hop3

Add Hop3 as a git remote:

```bash
git remote add hop3 hop3@your-server.com:your-app
```

Deploy:

```bash
git push hop3 main
```

You'll see the build stream by: toolchain detection, dependency install, the proxy being configured, the app coming up. A Coolify deploy would also build an image and schedule a container, two steps Hop3 skips unless you opted into the Docker builder. The app runs directly on the host, driven by your `hop3.toml`.

You can also deploy without git by running `hop3 deploy` from the app directory, which uploads the current source. That suits a first cutover, before you've wired up the remote.

## Step 6: Point Your Domain

Update your DNS to point at the new server:

```
your-app.example.com  A  your-server-ip
```

Once Let's Encrypt is configured on the server, Hop3 requests a certificate for the domain at deploy time. Out of the box, a freshly installed server serves a self-signed certificate until you point it at an ACME provider. Verify over the self-signed cert first, then switch DNS and let the real certificate issue. Coolify did this for you automatically. In Hop3, ACME is a server-level setting you configure once for all apps.

## Common Migration Notes

### Build Pack vs Toolchain

Coolify builds with Nixpacks by default, or with your `Dockerfile` if one is present, and always produces a container. Hop3 auto-detects the language and uses a native toolchain. Most apps build unchanged.

| Coolify build | Hop3 |
|---------------|------|
| Nixpacks (Python detected) | `python` (auto-detected) |
| Nixpacks (Node detected) | `node` (auto-detected) |
| Nixpacks (Go / Ruby / …) | corresponding toolchain (auto-detected) |
| Custom `Dockerfile` | `[build] builder = "docker"` |

If you relied on Nixpacks only to get a build, the native toolchain usually replaces it with nothing for you to configure. If you maintained a `Dockerfile` and want to keep it, tell Hop3 to use it:

```toml
[build]
builder = "docker"
```

For a multi-language app (say, Python with a Node-built frontend), drive the extra step from the `[build]` section instead of a multi-stage Dockerfile:

```toml
[build]
toolchain = "python"
before-build = "npm install && npm run build"
```

And if reproducibility is what drew you to a containerised build in the first place, the Nix builder gives you that without Docker:

```toml
[build]
builder = "nix"
```

### Scheduled Jobs

Coolify has scheduled tasks (cron-style jobs you define per resource). In Hop3, run a scheduler as a worker process:

```toml
[run.workers]
scheduler = "celery -A myapp beat"
```

Or use system cron on the server for occasional housekeeping tasks.

### Health Checks

Coolify polls a health-check endpoint before marking a deploy live. Declare the equivalent in Hop3 so it does the same:

```toml
[healthcheck]
path = "/health/"
timeout = 30
retries = 5
```

### Resource Limits

Coolify lets you cap a container's CPU and memory through Docker. Hop3 has a `[limits]` section: the Docker builder applies it to the container, and native and Nix builds run under a cgroup v2 cap that hop3-rootd sets up. A cap the server cannot apply aborts the deploy with a clear message.

## Command Mapping

| Coolify concept / action | Hop3 Command |
|--------------------------|--------------|
| Create an application | `hop3 app create` (or just the first `git push`) |
| List applications | `hop3 app list` |
| Application details / status | `hop3 app status --app X` |
| View environment variables | `hop3 env show --app X` |
| Set an environment variable | `hop3 env set K=V --app X` |
| View logs | `hop3 app logs --app X` |
| Running processes | `hop3 ps --app X` |
| Scale a process | `hop3 ps scale --app X web=N` |
| Restart | `hop3 app restart --app X` |
| Run a one-off command | `hop3 app run --app X` |
| Provision a database / service | `hop3 addon create` + `hop3 addon attach` |
| Database details | `hop3 addon show <name>` |
| Add a domain | `hop3 domain add <host> --app X` |
| Stop an application | `hop3 app stop --app X` |

## What You Gain, What You Trade

You're already self-hosting, so your server bill is yours either way. But the *resource* story does change. Coolify runs every app and every database in a container, with the Docker daemon, per-service overhead, and the management surface that comes with it. Hop3 runs apps natively, so the same workloads can fit on a smaller VPS, and there's simply less between your app and the host.

**You gain** a lighter, native-by-default runtime (no container layer unless you ask for one) and a declarative `hop3.toml` you can review and version. You also get native multi-language builds without minding Nixpacks or a Dockerfile, a reverse-proxy you can choose (Nginx, Caddy, Traefik), and built-in backups.

**You trade** Coolify's breadth. Coolify's one-click service catalogue is larger than Hop3's four data addons. Coolify also has the richer web UI, where Hop3 works CLI-first. If you relied on the catalogue for exotic datastores, you'll run those as external services and point env vars at them. Hop3 covers the common stack natively: a web app, a Postgres database, maybe Redis and object storage.

Hop3 runs on a single server, in one region. Scaling is manual, via `hop3 ps scale`. There are no review apps or deployment pipelines yet, and multi-factor authentication is deferred. If your Coolify usage was a single server running a handful of apps and their databases, Hop3 fits that shape directly. If you leaned on Coolify's broader service catalogue or its UI-driven multi-server management, weigh those gaps before you commit.

## Rollback Plan

The safe way to migrate is to keep Coolify running until you're confident:

1. Deploy to Hop3 on a fresh server with a test domain (or `/etc/hosts` entry).
2. Verify that the app, database, volumes, and workers all behave.
3. Switch DNS to the Hop3 server.
4. Keep the Coolify deployment running for a week or two.
5. Tear down the Coolify app and its containers once you're confident.

Because your Hop3 configuration now lives in `hop3.toml` in your repo, rolling forward to another server later is another `git push`.

## Getting Help

- [Hop3 Documentation](https://hop3.cloud)
- [GitHub Issues](https://github.com/abilian/hop3/issues)
- [Troubleshooting Guide](/guides/troubleshooting/)

---

*Coming from a different platform? The concepts are similar. Check the [Getting Started guide](/get-started/) for a fresh start.*
