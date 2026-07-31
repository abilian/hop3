# Migrating from Platform.sh to Hop3

Platform.sh (and its successor Upsun) is a capable managed platform: git-driven deploys, branch-as-environment with review apps, and a fleet of managed services described declaratively in YAML. It's also YAML-heavy and priced for teams with a budget to match. If you're moving because you want predictable cost, full control of your data, or simply fewer moving parts, Hop3 gives you a familiar git-push deployment workflow on a server you own — with the configuration collapsed into a single `hop3.toml` file. This guide helps you migrate an existing Platform.sh app to Hop3.

## What's Similar

The core mental model carries over almost unchanged:

| Platform.sh | Hop3 |
|-------------|------|
| `git push` to deploy | `git push hop3 main` |
| `.platform.app.yaml` | `hop3.toml` |
| build hook | `[build] before-build` |
| deploy hook | `[run] before-run` |
| managed PostgreSQL/MySQL/Redis | `hop3 addon create` |
| `relationships` inject credentials | addon attach injects the URL |
| `mounts` | `[[volumes]]` |
| `platform environment:list` | `hop3 app list` |

You still push git, you still declare your build and run steps, and your database credentials are still injected for you. The big change is consolidation: where Platform.sh splits configuration across `.platform.app.yaml`, `.platform/services.yaml`, and `.platform/routes.yaml`, Hop3 keeps everything in one `hop3.toml`.

One syntactic note: the Hop3 CLI uses spaces, not colons, and the app you're targeting is always the `--app` flag rather than part of the command. So `platform variable:set FOO=bar -e main` becomes `hop3 env set FOO=bar --app myapp`.

## What's Different

| Platform.sh | Hop3 |
|-------------|------|
| Managed platform | Self-hosted |
| Branch-as-environment + review apps | Not supported — deploy staging apps by name |
| Automatic scaling | Manual scaling (`hop3 ps scale`) |
| Many managed services (Elasticsearch, RabbitMQ, …) | PostgreSQL, MySQL, Redis, S3/MinIO — and growing |
| Multi-region, grid/dedicated tiers | Single server |
| YAML across three files | One `hop3.toml` |

Hop3 is simpler and cheaper, and you own the box. There is a real trade-off: **Platform.sh's branch-as-environment and review apps have no Hop3 equivalent**, and its richer managed services — Elasticsearch, RabbitMQ, and friends — aren't Hop3 addons. We come back to both below; neither is a dealbreaker, but both change how you work.

## Step 1: Set Up Your Hop3 Server

Provision a server (Ubuntu 24.04 LTS or later recommended; Debian, Fedora, and Rocky/Alma also work) and install Hop3:

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

## Step 2: Export Your Platform.sh Configuration

Pull your current environment variables off Platform.sh so you can carry over the application-level ones:

```bash
platform variable:list -e main
```

Note which variables you set yourself versus the ones Platform.sh injects from `relationships` (database, cache, search). You only carry over the former — Hop3 injects the addon URLs on its own (see Step 4). Drop:

- `DATABASE_URL` / the `database` relationship (Hop3's addon sets it)
- `REDIS_URL` / the `redis` relationship (Hop3's addon sets it)
- `PORT` (Hop3 sets `$PORT` automatically)
- Anything under `PLATFORM_*` (Platform.sh runtime metadata)

## Step 3: Translate Your YAML to hop3.toml

This is the heart of the migration. Platform.sh spreads configuration across three YAML files; Hop3 reads one TOML file. There is no automatic importer for Platform.sh config — Hop3's only config importer converts a `Procfile` (`hop3 app migrate procfile <dir>`), so the YAML translation is done by hand. It's mechanical once you see the mapping.

A representative Platform.sh `.platform.app.yaml`:

```yaml
name: app
type: python:3.12

relationships:
  database: "db:postgresql"
  cache: "rediscache:redis"

mounts:
  "var/uploads":
    source: local
    source_path: uploads

web:
  commands:
    start: "gunicorn -b $PORT myapp.wsgi"

workers:
  queue:
    commands:
      start: "celery -A myapp worker"

hooks:
  build: "pip install -r requirements.txt && npm ci && npm run build"
  deploy: "python manage.py migrate --noinput"

crons:
  cleanup:
    spec: "0 * * * *"
    commands:
      start: "python manage.py cleanup"
```

The matching `.platform/services.yaml`:

```yaml
db:
  type: postgresql:15
  disk: 2048
rediscache:
  type: redis:7
```

And `.platform/routes.yaml`:

```yaml
"https://{default}/":
  type: upstream
  upstream: "app:http"
```

That whole stack becomes one `hop3.toml`:

```toml
[metadata]
id = "myapp"

[build]
toolchain = "python"
before-build = "npm ci && npm run build"

[env]
# Application variables from `platform variable:list` (NOT the relationship URLs)
SECRET_KEY = "your-secret-key"
DJANGO_SETTINGS_MODULE = "myapp.settings.production"

[run]
start = "gunicorn -b 0.0.0.0:$PORT myapp.wsgi"
before-run = ["python manage.py migrate --noinput"]

[run.workers]
queue = "celery -A myapp worker"

[[volumes]]
name = "uploads"
target = "var/uploads"

[healthcheck]
path = "/health/"

[domains]
list = ["myapp.example.com"]
```

The mapping, primitive by primitive:

| Platform.sh | Hop3 |
|-------------|------|
| `.platform.app.yaml` `type:` | `[build] toolchain` (auto-detected, so often omittable) |
| `hooks.build` | `[build] before-build` |
| `hooks.deploy` | `[run] before-run` |
| `web.commands.start` | `[run] start` (or a `Procfile` `web:` line) |
| `workers.*.commands.start` | `[run.workers]` entries |
| `mounts` (writable dirs) | `[[volumes]]` |
| `relationships` | addon attach (Hop3 injects the URL) |
| `.platform/services.yaml` | `hop3 addon create <type> <name>` |
| `.platform/routes.yaml` | `[domains]` + `hop3 domain add` (Hop3 generates the nginx config) |
| `crons` | system cron (see below) |
| `resources` / sizes | `[limits]` (Docker builder) and `hop3 ps scale` |

A few notes on the translation:

- **`type:` → toolchain.** Hop3 auto-detects the language (Python, Node.js, Go, Ruby, Rust, Java, PHP, Elixir, .NET) from your project files, so you can often drop `[build] toolchain` entirely. Multi-language builds — your Python app that also compiles a JS bundle — map cleanly: keep the primary toolchain and put the asset build in `before-build`, exactly as the example does.
- **`web` → `$PORT`.** Platform.sh exports `$PORT`; so does Hop3. Bind to it in your start command and the reverse proxy routes to you.
- **`relationships` are the part that disappears.** On Platform.sh you map a relationship name to a service and read the injected credentials. On Hop3 you create the addon and attach it, and Hop3 injects `DATABASE_URL` / `REDIS_URL` for you — there is no relationship block to write. Step 4 covers this.
- **No automatic importer.** Don't reach for an `import` or `convert` command — there isn't one for Platform.sh YAML. Translate it by hand using the table above. If your app happens to have a `Procfile`, `hop3 app migrate procfile <dir>` will scaffold the process model into `hop3.toml` for you as a starting point.

## Step 4: Migrate Your Services and Data

### Services → addons

Each entry in `services.yaml` that Hop3 supports becomes an addon you create and attach. Hop3 ships PostgreSQL, MySQL, Redis, and S3/MinIO — and growing.

```bash
# From services.yaml: db (postgresql) and rediscache (redis)
hop3 addon create postgres myapp-db
hop3 addon attach myapp-db --app myapp

hop3 addon create redis myapp-cache
hop3 addon attach myapp-cache --app myapp
```

Attaching injects the connection variables (`DATABASE_URL`, `REDIS_URL`) into the app's environment — this is the Hop3 equivalent of a Platform.sh `relationship`, except you don't declare it in config, you attach it once. Inspect the result with:

```bash
hop3 addon show myapp-db
```

### Database migration

Export from Platform.sh over its SSH tunnel and import into the Hop3 addon:

```bash
# Export from Platform.sh
platform db:dump -e main --file dump.sql

# Stream it straight into the Hop3 addon (no SSH dance, no psql by hand)
hop3 addon postgres import myapp-db --confirm=myapp-db < dump.sql
```

If you use Postgres extensions (e.g. `pg_stat_statements`, `pgvector`), enable them through the addon command — they're allow-listed, so only the ones Hop3 supports will install:

```bash
hop3 addon postgres extensions myapp-db pg_stat_statements
```

### Redis

Most Redis usage is cache, so starting fresh is usually fine. If you need the data, dump from Platform.sh and import:

```bash
hop3 addon redis import myapp-cache --confirm=myapp-cache < dump.rdb
```

### The services Hop3 doesn't have

If your `services.yaml` lists **Elasticsearch, OpenSearch, RabbitMQ, Kafka, Memcached, MongoDB**, or similar, stop here — those are not Hop3 addons. Two options:

1. **Run them externally** and point `[env]` at the managed URL. Hop3 doesn't care where a service lives; if your app reads `ELASTICSEARCH_URL` from the environment, set it:

   ```bash
   hop3 env set ELASTICSEARCH_URL=https://es.example.com:9243 --app myapp
   ```

   The same trick keeps an existing managed database you're not ready to move: leave it where it is and point `DATABASE_URL` at it instead of creating an addon.

2. **Drop the dependency** if it was incidental (a search index you can rebuild from Postgres, a queue you can replace with a simpler worker).

This is the single biggest difference for a Platform.sh user with a rich service graph. Plan for it before you cut over.

## Step 5: Deploy to Hop3

Add Hop3 as a git remote and push:

```bash
git remote add hop3 hop3@your-server.com:myapp
git push hop3 main
```

(Equivalently, from the project directory: `hop3 deploy`.) Hop3 detects the language, runs your `before-build`, builds the app, runs `before-run`, configures nginx, and starts the workers you declared.

## Step 6: Routes and Domains

Platform.sh `routes.yaml` maps hostnames to upstreams; Hop3 generates the nginx config for you from the app's bound hostnames. You declared them in `[domains]` above; you can also add them imperatively:

```bash
hop3 domain add myapp.example.com --app myapp
```

Point your DNS at the server:

```
myapp.example.com  A  your-server-ip
```

Out of the box a fresh server serves a self-signed certificate. Once you've pointed the server at an ACME provider (Let's Encrypt), Hop3 requests a real certificate for the domain at deploy time.

## Common Migration Issues

### Workers and the process model

Platform.sh's `web` command maps onto Hop3's `[run] start` (the main process), and each entry under `workers` becomes a named entry under `[run.workers]`. If you'd rather keep the whole process model in the familiar format, a `Procfile` works too — both are supported. Scale each process type manually:

```bash
hop3 ps scale myapp web=3 queue=2
```

There's no autoscaling: scaling is a deliberate `ps scale` call, not a reaction to load.

### Crons

Platform.sh `crons` don't have a direct config equivalent. Use system cron on the server, invoking your command through the app context:

```bash
ssh root@your-server.com
crontab -e
# 0 * * * *  hop3 app run --app myapp python manage.py cleanup
```

A short-lived scheduled task can also live as a worker if it self-schedules (e.g. Celery beat), but for "run this every hour" jobs, system cron is the simplest mapping.

### Mounts → volumes

A Platform.sh `mount` is a writable directory that survives deploys. Hop3's `[[volumes]]` is the same idea — and you need it, because each deploy replaces the source tree, so anything written inside it is lost otherwise. List every writable path your app expects (`uploads/`, `var/`, a SQLite file) as a `[[volumes]]` entry.

### Runtime versions

Platform.sh pins the runtime in `type: python:3.12`. Hop3 uses the system runtime by default. For a specific version, use the Nix builder or the Docker builder:

```toml
[build]
builder = "docker"
```

The Docker builder is also where `[limits]` (memory/CPU caps, the rough analogue of Platform.sh resource sizing) is enforced.

### Branch-as-environment and review apps

This is the workflow gap. Platform.sh gives you an isolated environment per branch and a review app per pull request, with data inherited from the parent. Hop3 has neither. Workarounds:

1. Deploy a staging app under its own name: `myapp-staging`.
2. Use branch-derived names for short-lived environments: `myapp-feature-x`.
3. Clone production data into a staging addon to seed it: `hop3 addon postgres clone myapp-db myapp-staging-db`.

It's manual where Platform.sh was automatic. If per-PR review apps are central to how your team ships, weigh that before migrating.

## Command Mapping

| Platform.sh Command | Hop3 Command |
|---------------------|--------------|
| `platform project:create` | `hop3 app create` |
| `platform project:list` | `hop3 app list` |
| `platform environment:info` | `hop3 app status --app X` |
| `platform variable:list` | `hop3 env show --app X` |
| `platform variable:set` | `hop3 env set K=V --app X` |
| `platform log --tail` | `hop3 app logs --app X` |
| `platform environment:restart` | `hop3 app restart --app X` |
| `platform ssh -- <cmd>` | `hop3 app run --app X <cmd>` |
| `platform db:dump` | `hop3 addon postgres export <name>` |
| `platform redis-cli` | `hop3 addon redis query <name> --command "..."` |
| `platform domain:add` | `hop3 domain add <host> --app X` |
| `platform environment:pause` | `hop3 app stop --app X` |
| `platform service:list` | `hop3 addon list --app X` |

## Cost and Lock-In

Platform.sh prices per project and per environment, and the YAML config — relationships, the three-file split, the platform-specific runtime types — is portable in spirit but not in practice: it only runs on Platform.sh. The value you get for that is real (managed everything, review apps, multi-region), but so is the bill and the coupling.

Hop3 inverts the trade. You run one VPS at VPS prices, your whole deployment is one `hop3.toml` that describes standard primitives (a toolchain, some workers, a Postgres addon, a volume), and nothing in it is bound to a vendor. The cost is the operational surface: you patch the server, you scale by hand, and you don't get review apps or Elasticsearch-as-a-checkbox. For a single app or a small fleet where those features were never load-bearing, that's a clear win. For a large team leaning hard on branch environments and a wide service graph, it's a genuine downgrade in convenience — go in with eyes open.

## Rollback Plan

Keep Platform.sh running until you're confident:

1. Deploy to Hop3 on a test domain (`myapp-staging.example.com`).
2. Verify the app, the database import, and every external service URL.
3. Switch DNS to the Hop3 server.
4. Keep the Platform.sh environment live for 1–2 weeks as a fallback.
5. Tear down the Platform.sh project once the Hop3 deployment has proven itself.

Because DNS is the only switch, rolling back is just pointing the record back at Platform.sh.

## Getting Help

- [Hop3 Documentation](https://hop3.cloud)
- [GitHub Issues](https://github.com/abilian/hop3/issues)

---

*Coming from a different platform? The primitives are the same. Check the [Getting Started guide](/get-started/) for a fresh start.*
