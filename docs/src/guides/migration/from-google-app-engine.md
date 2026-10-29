# Migrating from Google App Engine to Hop3

Thinking about leaving Google App Engine? Maybe the scaling is invisible right up until the bill arrives, with no way to tell which request cost what. Maybe your app is wired into Cloud Datastore and a handful of Cloud APIs, and that lock-in has started to feel more like a fence than a convenience. Maybe you want the whole thing on one box you can SSH into, reason about, and pay for at a flat rate. Whatever the reason, Hop3 gives you a deploy-from-a-config-file workflow that App Engine users will find familiar, on infrastructure you own. This guide helps you migrate existing App Engine apps to Hop3.

Weigh the trade-off before you spend an afternoon on it. App Engine scales a stateless app from zero to a flood of traffic across Google's edge, automatically, with no server for you to think about. Hop3 is a single always-on server. You give up scale-to-zero and Google's autoscaler. In exchange you get one predictable bill, one place to look when something breaks, and your data in one jurisdiction you chose. If your app needs to absorb spiky, planet-scale traffic with no operator in the loop, stay on App Engine. If it's a web app, a database and a couple of background jobs, and the "scales to billions" pitch was aspirational, Hop3 will feel like a relief.

## What's Similar

Hop3 was designed with the same deploy-from-a-config-file workflow App Engine users already know:

| Google App Engine | Hop3 |
|-------------------|------|
| `app.yaml` | `hop3.toml` |
| `gcloud app deploy` | `git push hop3 main` (or `hop3 deploy`) |
| `env_variables` | `[env]` in `hop3.toml` / `hop3 env set` |
| `runtime: python312` | native toolchain (auto-detected) |
| `gcloud app logs tail` | `hop3 app logs` |

The shape is the same: one declarative file in your repo, one command to ship. Where App Engine drives everything through `gcloud app <verb>`, Hop3 uses space-separated `hop3 <noun> <verb>`. The app you're targeting is always the `--app` flag, never the active gcloud project. So `gcloud app deploy` against project `myapp` becomes `hop3 deploy --app myapp` (or `git push hop3 main` from the repo).

There's no automated `app.yaml` importer. The only config converter Hop3 ships is `hop3 app migrate procfile`, which scaffolds a `hop3.toml` from a `Procfile`, and App Engine doesn't use one. You translate `app.yaml` by hand; the translation is short and mechanical, and the section below walks through it field by field.

## What's Different

| Google App Engine | Hop3 |
|-------------------|------|
| Scales to zero, autoscaling | Single always-on server |
| Automatic / basic / manual scaling | Manual via `hop3 ps scale` |
| Cloud Datastore, Cloud SQL, Memcache, Task Queues | PostgreSQL, MySQL, Redis, S3 (Garage), and growing |
| Multiple `services` (microservices) | One app per service |
| Google edge / global serving | One server, one region |

Hop3 is simpler. You manage one server instead of a project full of Google-managed services.

## Step 1: Set Up Your Hop3 Server

Provision a server (Ubuntu 24.04 LTS recommended; Debian, Fedora, and Rocky/Alma also work) and install Hop3:

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

## Step 2: Export Your App Engine Configuration

Your `app.yaml` is the obvious starting point: copy it somewhere handy. Its `env_variables` block is the easy part. The harder part is the configuration that lives outside `app.yaml`: connection strings and credentials for Cloud SQL, API keys for the Google services your code calls, anything set through Secret Manager. List them so you know what you'll need to set again:

```bash
# What env vars the deployed version is running with
gcloud app versions describe VERSION --service default

# Cloud SQL instances you may be pointing at
gcloud sql instances list
```

Then plan to remove the App Engine-specific entries that Hop3 sets for you or that mean nothing off the platform:

- `DATABASE_URL` (set by a Hop3 addon, if you move the database to one)
- `PORT` (set by Hop3; App Engine also injects it, so your app already reads it)
- `GAE_*` variables (`GAE_APPLICATION`, `GAE_SERVICE`, `GAE_VERSION`, `GAE_INSTANCE`, …), which have no meaning off App Engine
- `GOOGLE_CLOUD_PROJECT` and anything that only resolves inside Google's metadata server

## Step 3: Translate app.yaml to hop3.toml

A representative `app.yaml` for a Python web app, with an entrypoint, env vars, automatic scaling and a health check, looks roughly like this:

```yaml
# app.yaml
runtime: python312
service: default

entrypoint: gunicorn -b :$PORT main:app

env_variables:
  SECRET_KEY: "your-secret-key"
  DJANGO_SETTINGS_MODULE: "myapp.settings.production"

automatic_scaling:
  min_instances: 0
  max_instances: 10

readiness_check:
  path: "/health/"
```

The same app as `hop3.toml`:

```toml
[metadata]
id = "your-app"

[build]
toolchain = "python"

[env]
DJANGO_SETTINGS_MODULE = "myapp.settings.production"

[run]
start = "gunicorn -b 0.0.0.0:$PORT main:app"
before-run = ["python manage.py migrate"]

[healthcheck]
path = "/health/"
```

The secret goes to the server, out of the repo:

```bash
hop3 env set --app your-app SECRET_KEY=-
```

`KEY=-` reads the value from a hidden prompt, so it never appears in your shell history.

Each App Engine primitive lands on a Hop3 one:

- **`service` → `[metadata].id`.** App Engine's `default` (and any other `service:`) maps to a Hop3 app name. Each App Engine service becomes its own Hop3 app; see "Multiple Services" below.
- **`runtime: python312` → a native toolchain.** Hop3 detects the language from the files in your repo (Python, Node.js, Go, Ruby, Java, PHP, .NET, and more), so you usually don't need to declare it. The explicit `toolchain = "python"` above makes it visible.
- **`entrypoint` → `[run].start`.** It must bind `0.0.0.0:$PORT`: Hop3 allocates the port at deploy time, and the reverse proxy routes to it by hostname. A `Procfile` `web:` line works too, if you'd rather keep one.
- **`env_variables` → `[env]`.** A direct copy for the plain settings, minus the platform-specific keys from Step 2. Secrets go through `hop3 env set`, as above.
- **`automatic_scaling` → manual `hop3 ps scale`.** This is the most visible thing you lose. It is the heart of the trade-off; see "Scaling" below.
- **`readiness_check` / `liveness_check` → `[healthcheck]`.** Same idea, one path.

## Step 4: Migrate Your Data

App Engine apps usually store data in one of two places, and they migrate very differently.

### Cloud SQL → a Hop3 addon (or keep it external)

Cloud SQL is a managed Postgres or MySQL, so it dumps and restores the ordinary way. Export it with the standard tools:

```bash
# Postgres via the Cloud SQL Auth Proxy
cloud-sql-proxy your-project:europe-west1:your-instance &
pg_dump "postgres://USER:PASSWORD@127.0.0.1:5432/your_app" \
    -Fc -f latest.dump
```

Then, on the Hop3 side, create the database addon and attach it to your app:

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
# Turn the dump into SQL and load it into the addon (where the hop3 CLI runs)
pg_restore --no-owner --no-acl -f latest.sql latest.dump
hop3 addon postgres import your-app-db --confirm=your-app-db < latest.sql
```

If you'd rather **keep Cloud SQL** for now (you're not ready to move the database, or other systems still talk to it), you don't have to migrate it at all. Skip the addon and set the existing instance's URL on the server (`hop3.toml` refuses a connection string with credentials in it):

```bash
hop3 env set --app your-app DATABASE_URL="postgresql://user:pass@your-cloud-sql-host:5432/mydb"
```

Your app talks to that database exactly as before, outside Hop3's management, until you adopt a Hop3 addon. You'll need to allow the Hop3 server's IP through Cloud SQL's authorized networks, or run the Cloud SQL Auth Proxy on the box.

### Cloud Datastore → there is no drop-in equivalent

This is the gap that matters most for App Engine users. **Hop3 has no equivalent of Cloud Datastore (Firestore in Datastore mode).** It's a Google-proprietary, schemaless, autoscaling document store, and nothing in Hop3 replaces it like for like. Migrating off it is a real piece of work:

- Export your entities (`gcloud datastore export`, or read them through the API).
- Model them as relational tables, or as JSONB columns, in the Hop3 **Postgres** addon, and rewrite the data-access layer that used the Datastore client library to use SQL.
- For many App Engine apps this is the bulk of the migration. If your app is Datastore-native, budget for it. That work is the cost of leaving Datastore's lock-in, which no config file pays.

### Memcache → Redis

App Engine's Memcache has no Hop3 equivalent either. Its use case, a fast key/value cache, maps cleanly onto the Redis addon:

```bash
hop3 addon create redis your-app-cache
hop3 addon attach your-app-cache --app your-app
```

Most cache data doesn't need migrating; let it warm up fresh. Rewrite the calls that used the Memcache API to talk to Redis (the app gets a `REDIS_URL` once the addon is attached).

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

On App Engine your app got `*.appspot.com`, and custom domains went through `gcloud app domain-mappings`. On Hop3 you point a record at your one server:

```
your-app.example.com  A  your-server-ip
```

Bind the hostname to the app:

```bash
hop3 domain add your-app.example.com --app your-app
```

Once Let's Encrypt is configured on the server, Hop3 requests a certificate for the domain at deploy time. Out of the box, a freshly installed server serves a self-signed certificate until you point it at an ACME provider.

## Common Migration Issues

### Multiple Services (Microservices)

App Engine lets one project hold several `services` (a `default` service, an `api` service, a `worker` service), each with an `app.yaml` and a scaling policy. Hop3 has no notion of services within an app: **each App Engine service becomes its own Hop3 app**. Deploy each one from its directory, with its app name:

```bash
hop3 deploy --app your-app-default
hop3 deploy --app your-app-api
hop3 deploy --app your-app-worker
```

Each gets a `hop3.toml`, a domain and a scale of its own. They share the server, so they reach each other over localhost, with no `8081-dot-...` URL routing and no internal load balancer. Shared services (a database, a cache) are addons you attach to each app that needs them.

### Standard vs Flexible, and Native vs Docker

App Engine made you choose between the **Standard** environment (sandboxed, fast cold starts, fixed runtimes) and **Flexible** (a container on a Compute Engine VM, any runtime, slower). Hop3 turns that choice into how you build:

- For most apps, let Hop3 detect a **native toolchain**, the analogue of Standard's "give me the runtime, run my code", with no container at all.
- If your App Engine Flexible app shipped a custom `Dockerfile` (`runtime: custom`), Hop3 builds the same image with the Docker builder:

```toml
[build]
builder = "docker"
```

There's also a Nix builder and a static-site builder for the cases in between. You're no longer picking a Google environment tier; you're picking a build strategy, and the default (native) covers most apps.

### Runtime Versions

App Engine pins the runtime in `app.yaml` (`runtime: python312`, `nodejs20`, …). Hop3's native toolchain uses the system runtime on your server (Python 3.11–3.13, depending on the OS). If you need a version the host doesn't provide, the Docker builder lets you pin it exactly:

```toml
[build]
builder = "docker"
```

### Scheduled Jobs (cron.yaml)

App Engine schedules background work with `cron.yaml`, which calls a URL on a schedule. Hop3 has two equivalents. For a long-running scheduler process, declare a worker in `hop3.toml`:

```toml
[run.workers]
scheduler = "celery -A myapp beat"
```

For the closer match to `cron.yaml` (run this command at this time), use cron with `hop3 app run`, which runs the command in the app's environment:

```bash
# On a machine where the hop3 CLI is signed in to the server
crontab -e
# Add: 0 * * * * hop3 app run --app your-app python manage.py cleanup
```

If your `cron.yaml` jobs worked by calling an HTTP endpoint, you can keep that shape: point a cron line at `curl https://your-app.example.com/tasks/cleanup`.

### Task Queues

App Engine Task Queues (and Cloud Tasks) have no managed Hop3 equivalent. For most apps the practical substitute is a worker process backed by the **Redis** addon, with a job queue like Celery, RQ or Sidekiq. Attach a Redis addon, run the queue's worker as a `[run.workers]` entry, and enqueue jobs from your web process. It lacks Cloud Tasks' retries and rate limits, but it covers the common "do this later, off the request path" need on one server.

### Scaling

After Datastore, this is the gap that matters most. App Engine's `automatic_scaling` (and `basic_scaling`) start and stop instances, down to zero, based on traffic, with no operator in the loop. Hop3 does not autoscale. You run a fixed number of processes on one always-on server and change that number yourself:

```bash
hop3 ps scale --app your-app web=3 worker=2
```

There's no scale-to-zero (the server is always on, which is also why the bill is flat), and no autoscaler reacting to a traffic spike. For a steady web app this is usually fine, and cheaper. For spiky, unpredictable, planet-scale traffic, App Engine earns its keep, and Hop3 isn't trying to replace it there.

## Command Mapping

| App Engine Command | Hop3 Command |
|--------------------|--------------|
| `gcloud app deploy` | `git push hop3 main` (or `hop3 deploy --app X`) |
| `gcloud app services list` | `hop3 app list` |
| `gcloud app describe` | `hop3 app status --app X` |
| `gcloud app versions describe` (env) | `hop3 env show --app X` |
| `gcloud app deploy` (with env change) | `hop3 env set --app X K=V`, then `hop3 app restart --app X` |
| `gcloud app logs tail` | `hop3 app logs --app X` |
| `gcloud app instances list` | `hop3 ps --app X` |
| `automatic_scaling` (in `app.yaml`) | `hop3 ps scale --app X web=N` |
| `gcloud app versions ...` (restart) | `hop3 app restart --app X` |
| `gcloud app instances ssh` | `hop3 app shell --app X` |
| One-off command | `hop3 app run --app X <command>` |
| `gcloud sql instances create` | `hop3 addon create postgres <name>` |
| (attach Cloud SQL) | `hop3 addon attach <name> --app X` |
| `gcloud app domain-mappings create` | `hop3 domain add <host> --app X` |

## Cost and Lock-In

App Engine's pricing is usage-based: instance-hours, plus Datastore reads, writes and storage, plus Cloud SQL, plus egress. That works until a traffic spike or a chatty Datastore access pattern shows up on the invoice, with no easy way to attribute the cost to a feature. Hop3's bill is a VPS: you know the number, and adding an app or a busier week doesn't change it.

| | Google App Engine | Hop3 (self-hosted) |
|-|-------------------|-------------------|
| Compute | instance-hours, autoscaled | fixed VPS |
| Database | Cloud SQL + Datastore ops | Postgres addon on the VPS |
| Cache / queues | Memcache + Task Queue ops | Redis addon on the VPS |
| Egress | metered | included (VPS allowance) |
| **Small app** | usage-based, hard to predict | ~$10/month (VPS) |
| **Medium app** | usage-based, hard to predict | ~$30/month (VPS) |

Lock-in matters more here. On App Engine your app is shaped around Google: the Datastore client library, the Task Queue API, Memcache, the metadata server, `appspot.com` hostnames. That's code written against Google's APIs, which no config file moves elsewhere. On Hop3 it's a standard web app, a Postgres you can `pg_dump`, a Redis, and a config file in your repo, all of which run anywhere. Getting *to* that portable shape means rewriting the Datastore, Memcache and Task Queue code, and that is the real cost of leaving App Engine. Once you've paid it, you're free of the platform, and if you ever leave Hop3 too, you leave with a standard app. The trade-off is the usual one: you manage the server, and you control everything on it.

## Rollback Plan

Keep your App Engine app serving during migration; a version you don't promote keeps running on its own URL:

1. Deploy to Hop3 with a test domain (or a subdomain you don't yet point users at)
2. Verify everything works against real data, especially the rewritten Datastore, Memcache and Task Queue paths
3. Switch DNS to point at your Hop3 server
4. Keep the App Engine version serving for 1–2 weeks
5. Run `gcloud app services delete` (and tear down Cloud SQL / Datastore) once you're confident

Because DNS is the cut-over switch, rollback is pointing the record back at App Engine. As long as you haven't deleted Datastore or Cloud SQL, no data has to move twice. If you migrated *off* Datastore, keep the original read-only until you're sure, since DNS alone can't re-point that path.

## Getting Help

- [Hop3 Documentation](https://hop3.cloud)
- [GitHub Issues](https://github.com/abilian/hop3/issues)
- [Troubleshooting Guide](/guides/troubleshooting/)

---

*Coming from a different platform? The concepts are similar. Check the [Getting Started guide](/get-started/) for a fresh start.*
