# Migrating from Dokku to Hop3

If you run Dokku, you already believe in the core idea behind Hop3: deploy with `git push`, describe your app with a `Procfile`, and keep the whole thing on a server you control. Of all the platforms you could migrate from, Dokku is the closest cousin. You're not changing your mental model — you're swapping one self-hosted PaaS for another, and most of what you know carries straight over.

So why move at all? The usual reasons: you want Hop3's declarative `hop3.toml` instead of remembering a chain of `dokku ...:set` commands, you want native multi-language toolchains without thinking about buildpacks or maintaining a Dockerfile, or you want Hop3's broader platform direction (built-in addons, reverse-proxy choice, backups). Whatever the reason, this guide walks an existing Dokku app over to Hop3, primitive by primitive.

## What's Similar

Dokku and Hop3 share the same skeleton, so the muscle memory transfers:

| Dokku | Hop3 |
|-------|------|
| `git push dokku main` | `git push hop3 main` |
| `Procfile` | `Procfile` (compatible) |
| `dokku config:set` | `hop3 env set` |
| `dokku postgres:create` + `postgres:link` | `hop3 addon create` + `hop3 addon attach` |
| `dokku domains:add` | `hop3 domain add` |
| `dokku ps:scale` | `hop3 ps scale` |

Your `Procfile` works unchanged. Your deployment workflow — commit, push, watch the build stream by — stays the same.

The one syntactic shift to internalize: Dokku uses a colon and a positional app (`dokku config:set FOO=bar myapp`), while Hop3 uses spaces and an `--app` flag (`hop3 env set FOO=bar --app myapp`). The target app is always the `--app` flag, never a positional argument and never a `verb:action` colon. So `dokku config:set FOO=bar myapp` becomes `hop3 env set FOO=bar --app myapp`.

## What's Different

| Dokku | Hop3 |
|-------|------|
| Imperative, per-command config | Declarative `hop3.toml` |
| Buildpacks / Dockerfile / herokuish | Native toolchains, Docker builder, or Nix builder |
| Large plugin ecosystem (many datastores) | PostgreSQL, MySQL, Redis, S3/MinIO — and growing |
| Manual scaling | Manual scaling |
| Single server | Single server |

The two big conceptual changes are worth calling out:

**Declarative config.** In Dokku, your app's configuration lives as accumulated state on the server: every `config:set`, every `domains:add`, every `ps:scale` is a command you ran once and have to remember. In Hop3 the same facts live in a `hop3.toml` checked into your repo. The server reads it on deploy. Your config becomes reviewable, diffable, and reproducible — re-deploying to a fresh server reproduces the app, rather than requiring you to replay a runbook of commands.

**Native toolchains instead of buildpacks.** Dokku builds with herokuish buildpacks by default, or a Dockerfile if you provide one. Hop3 auto-detects the language and uses a native toolchain (Python, Node.js, Go, Ruby, Rust, Java, PHP, Elixir, .NET). If you've been maintaining a Dockerfile purely to get a build, you can usually drop it. If you'd rather keep your Dockerfile, Hop3 has a Docker builder; and there's a Nix builder if you want fully reproducible builds.

One caveat to state up front: Dokku's plugin ecosystem is large, and people lean on it for datastores Hop3 doesn't ship — MongoDB, RabbitMQ, Elasticsearch, and more. Hop3's built-in addons are PostgreSQL, MySQL, Redis, and S3/MinIO. If your app depends on something outside that set, see [Data and Addon Migration](#step-4-migrate-your-data-and-addons) below — you keep it as an external service and point an env var at it.

## Step 1: Set Up Your Hop3 Server

You already self-host, so this part is quick. Provision a server (Ubuntu 24.04 LTS or later recommended; Debian, Fedora, and Rocky/Alma also work) and install Hop3:

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

You can run Hop3 on the same box as Dokku during the migration, but the cleaner path is a fresh server — that way the two never contend for ports 80/443, and you can cut over with DNS when you're ready.

## Step 2: Export Your Dokku Configuration

Pull the environment variables out of your Dokku app:

```bash
dokku config:show your-app
```

Save them somewhere you can edit. Review the list and drop the ones Hop3 manages for you:

- `DATABASE_URL` — will be set by the Hop3 Postgres addon
- `REDIS_URL` — will be set by the Hop3 Redis addon
- `PORT` — auto-set by Hop3 (your app binds to `$PORT`, same as on Dokku)
- Any `DOKKU_*` variables

While you're at it, note your current process scaling (`dokku ps:report your-app`) and your domains (`dokku domains:report your-app`) — you'll re-declare both in `hop3.toml`.

## Step 3: Add hop3.toml

This is the heart of the migration: turning the imperative state you built up with `dokku ...:set` commands into one declarative file. Your `Procfile` keeps working as-is, but `hop3.toml` is where the rest of your config now lives.

Suppose your Dokku app was configured like this:

```bash
dokku config:set your-app SECRET_KEY=... RAILS_ENV=production
dokku domains:add your-app your-app.example.com
dokku ps:scale your-app web=2 worker=1
dokku postgres:create your-app-db
dokku postgres:link your-app-db your-app
```

The equivalent `hop3.toml` gathers all of that into one place:

```toml
[metadata]
id = "your-app"

[build]
toolchain = "ruby"

[env]
# Copy the variables you kept from `dokku config:show`
SECRET_KEY = "your-secret-key"
RAILS_ENV = "production"

[run]
before-run = ["bundle exec rails db:migrate"]

[run.workers]
worker = "bundle exec sidekiq"

[[addons]]
type = "postgres"

[domains]
list = ["your-app.example.com"]

[healthcheck]
path = "/up"
```

A few notes on the translation:

- Your `Procfile`'s `web:` process is detected and run automatically; declare extra worker processes under `[run.workers]` (the equivalent of the non-`web` lines in your Procfile or your `ps:scale` workers).
- `before-run` replaces the release-phase command you'd run by hand or in a Dokku `app.json` predeploy hook — migrations, asset precompiles, and the like.
- `[[addons]]` declares the database your app needs; attaching it (next step) injects `DATABASE_URL`, exactly as `postgres:link` did.
- `[domains]` is the declarative form of `dokku domains:add`. You can still add domains imperatively later with `hop3 domain add`.

If you'd rather not write the file by hand, Hop3 can scaffold a starting point from your existing `Procfile`:

```bash
cd your-app/
hop3 app migrate procfile . --dry-run
```

## Step 4: Migrate Your Data and Addons

### PostgreSQL

On Dokku you provisioned the database with the postgres plugin (`dokku postgres:create` + `postgres:link`). In Hop3 you create the addon and attach it:

```bash
hop3 addon create postgres your-app-db
hop3 addon attach your-app-db --app your-app
```

Get the connection details:

```bash
hop3 addon show your-app-db
```

Now move your data. Export from Dokku's database container and import on the Hop3 side:

```bash
# On the Dokku host: dump the database
dokku postgres:export your-app-db > your-app.dump

# Copy the dump to the Hop3 server
scp your-app.dump root@your-server.com:/tmp/

# SSH to the Hop3 server and import
ssh root@your-server.com
sudo -u postgres pg_restore --verbose --no-owner \
    -d your_app_db /tmp/your-app.dump
```

If your Dokku app used Postgres extensions (for example `pg_stat_statements` or `pgcrypto`), enable them through the addon command — no manual `psql` needed:

```bash
hop3 addon postgres extensions your-app-db pg_stat_statements
```

Extensions are allow-listed, so only the ones Hop3 ships support for will install.

### Redis

If your Dokku app used the redis plugin, create and attach a Redis addon the same way:

```bash
hop3 addon create redis your-app-cache
hop3 addon attach your-app-cache --app your-app
```

Most Redis data is cache and can start fresh. If you do need to carry it over, export from Dokku's redis container and reload it on the new server — but for the common case, attaching a fresh Redis addon and letting it warm up is the simpler path.

### MySQL and object storage

Dokku also has plugins for MySQL and for S3-compatible object storage; both map directly:

```bash
hop3 addon create mysql your-app-db
hop3 addon create s3 your-app-storage
```

### Addons Hop3 doesn't ship

This is the one place where Dokku's larger plugin ecosystem shows. If your app depends on a datastore outside Hop3's set — MongoDB, RabbitMQ, Elasticsearch, and so on — Hop3 won't provision it for you. The pragmatic path is to keep running that service (on its own box, or as a managed offering) and point an env var at it:

```bash
hop3 env set --app your-app MONGODB_URL=mongodb://user:pass@db.internal:27017/yourapp
```

Your app connects to it exactly as it did under Dokku; the only difference is that Hop3 isn't managing its lifecycle. This is the same approach you'd take to keep an existing managed database during a phased migration.

## Step 5: Deploy to Hop3

The git remote shifts from `dokku@host:app` to `hop3@your-server.com:app`. Add the new remote:

```bash
git remote add hop3 hop3@your-server.com:your-app
```

Deploy:

```bash
git push hop3 main
```

You'll see the build stream by — toolchain detection, dependency install, the proxy being configured, the app coming up — just like watching a Dokku deploy, only with `hop3.toml` driving the configuration.

## Step 6: Point Your Domain

Update your DNS to point at the new server:

```
your-app.example.com  A  your-server-ip
```

Once Let's Encrypt is configured on the server, Hop3 requests a certificate for the domain at deploy time. Out of the box, a freshly installed server serves a self-signed certificate until you point it at an ACME provider — so verify over the self-signed cert first, then switch DNS and let the real certificate issue.

## Common Migration Notes

### Buildpacks and Dockerfiles vs Toolchains

Dokku builds with herokuish buildpacks by default, or with your `Dockerfile` if one is present. Hop3 auto-detects the language and uses a native toolchain. Most apps build unchanged.

| Dokku build | Hop3 |
|-------------|------|
| `heroku-buildpack-python` | `python` (auto-detected) |
| `heroku-buildpack-nodejs` | `node` (auto-detected) |
| `heroku-buildpack-ruby` | `ruby` (auto-detected) |
| Custom `Dockerfile` | `[build] builder = "docker"` |

If you were keeping a `Dockerfile` only to satisfy Dokku's builder, you can usually drop it and let the native toolchain take over. If you genuinely want the container build, keep the `Dockerfile` and tell Hop3 to use it:

```toml
[build]
builder = "docker"
```

For a multi-language app (say, Python with a Node-built frontend), drive the extra step from the `[build]` section:

```toml
[build]
toolchain = "python"
before-build = "npm install && npm run build"
```

### Scheduled Jobs

Dokku doesn't ship a scheduler; people usually add a cron plugin or a worker process. In Hop3, run a scheduler as a worker:

```toml
[run.workers]
scheduler = "celery -A myapp beat"
```

Or use system cron on the server for occasional housekeeping tasks.

### Zero-Downtime and Checks

Dokku's `zero-downtime` deploys and `CHECKS` file have a counterpart in Hop3's healthcheck. Declare the endpoint Hop3 should poll before considering a deploy live:

```toml
[healthcheck]
path = "/up"
timeout = 30
interval = 60
```

## Command Mapping

| Dokku Command | Hop3 Command |
|---------------|--------------|
| `dokku apps:create` | `hop3 app create` (or just the first `git push`) |
| `dokku apps:list` | `hop3 app list` |
| `dokku apps:report` | `hop3 app status --app X` |
| `dokku config:show` | `hop3 env show --app X` |
| `dokku config:set` | `hop3 env set K=V --app X` |
| `dokku logs -t` | `hop3 app logs --app X` |
| `dokku ps:report` | `hop3 ps --app X` |
| `dokku ps:scale` | `hop3 ps scale --app X web=N` |
| `dokku ps:restart` | `hop3 app restart --app X` |
| `dokku run` | `hop3 app run --app X` |
| `dokku postgres:create` + `postgres:link` | `hop3 addon create` + `hop3 addon attach` |
| `dokku postgres:info` | `hop3 addon show <name>` |
| `dokku domains:add` | `hop3 domain add <host> --app X` |
| `dokku ps:stop` | `hop3 app stop --app X` |

## What You Gain, What You Trade

You're already self-hosting, so this isn't a cost story the way leaving a commercial PaaS would be — your server bill doesn't change. What changes is the shape of the work:

**You gain** a declarative, version-controlled description of each app (no more reconstructing config from a runbook of `dokku` commands), native multi-language builds without minding buildpacks or a Dockerfile, and a platform with reverse-proxy choice (Nginx, Caddy, Traefik), built-in backups, and a growing addon set.

**You trade** Dokku's large plugin ecosystem. If you relied on community plugins for exotic datastores, you'll run those as external services and point env vars at them. For the common stack — a web app, a Postgres database, maybe Redis and object storage — Hop3 covers it natively.

It's a sidegrade in setup effort and an upgrade in how your configuration is expressed. Be clear-eyed about the gaps, though: like Dokku, Hop3 is a single-server platform. There's no multi-region, no cluster, no edge; scaling is manual via `hop3 ps scale` (no autoscaling); and there are no review apps or deployment pipelines yet. If you came to Dokku precisely because you didn't want any of that, you'll feel at home.

## Rollback Plan

The safe way to migrate is to keep Dokku running until you're confident:

1. Deploy to Hop3 on a fresh server with a test domain (or `/etc/hosts` entry).
2. Verify the app, its database, and its workers all behave.
3. Switch DNS to the Hop3 server.
4. Keep the Dokku app running for a week or two.
5. Tear down the Dokku app once you're confident.

Because your Hop3 configuration now lives in `hop3.toml` in your repo, rolling forward to another server later is just another `git push` — which is the point.

## Getting Help

- [Hop3 Documentation](https://hop3.cloud)
- [GitHub Issues](https://github.com/abilian/hop3/issues)
- [Troubleshooting Guide](/guides/troubleshooting/)

---

*Coming from a different platform? The concepts are similar. Check the [Getting Started guide](/get-started/) for a fresh start.*
