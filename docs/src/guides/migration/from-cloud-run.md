# Migrating from Google Cloud Run to Hop3

Thinking about leaving Google Cloud Run? Maybe the per-request billing was supposed to be cheap and the invoice surprised you. Maybe a cold start added a second to the first request after every idle stretch. Maybe you're tired of stitching together Secret Manager, a Cloud SQL connector, a VPC connector, and an IAM policy just to run one web service. Or maybe the service is busy enough that it never actually scales to zero, so you're paying for an always-on container with a serverless tax on top. Whatever the reason, Hop3 runs the same container you already ship, on a single server you understand. This guide helps you migrate existing Cloud Run services to Hop3.

The trade-off is worth stating up front, before you spend an afternoon on it. Cloud Run is built for elastic, request-driven workloads: it scales to zero when idle, spins up instances on demand, and bills you per request and per CPU-second of actual work. Hop3 does none of that. It keeps your process warm on one box, all the time, for a flat monthly cost. You give up scale-to-zero and per-request autoscaling, and you give up Google's multi-region front end. In exchange you get no cold starts, one predictable bill, and your data in exactly one place you chose. If your service is spiky — quiet most of the day, then a thundering herd — Cloud Run's elasticity is genuinely earning its keep, and you should keep it. If it's a web app that's effectively always on anyway, Hop3 will feel both cheaper and simpler. And because you already ship a container, the move is small.

## What's Similar

Hop3 was designed with the same ship-a-container, configure-from-a-file workflow Cloud Run users already know:

| Cloud Run | Hop3 |
|-----------|------|
| Container image (Dockerfile) | `[build] builder = "docker"` |
| `gcloud run deploy` | `git push hop3 main` (or `hop3 deploy`) |
| `--set-env-vars` / `--update-env-vars` | `hop3 env set` |
| Cloud SQL + connector | `hop3 addon create postgres` |
| `gcloud run services logs read` | `hop3 app logs` |

The shape is the same: a container, some environment, one command to ship. Where Cloud Run drives everything through `gcloud run <verb>` with a long string of flags, Hop3 uses space-separated `hop3 <noun> <verb>`, and the app you're targeting is always the `--app` flag rather than baked into a `gcloud config` project context. So `gcloud run deploy myapp --set-env-vars FOO=bar` becomes, roughly, `hop3 env set FOO=bar --app myapp` followed by a deploy.

There's no automated importer for Cloud Run's `service.yaml` (the Knative manifest) — the translation is short and mechanical, and the sections below walk through it field by field. (If your service keeps its process model in a `Procfile` rather than a container entrypoint, `hop3 app migrate procfile . --dry-run` will scaffold a starting `hop3.toml` from that. There is no importer for `service.yaml`, `cloudbuild.yaml`, or any other format — that one's by hand.)

## What's Different

| Cloud Run | Hop3 |
|-----------|------|
| Scale to zero | Always on (process kept warm) |
| Per-request autoscaling | Manual via `hop3 ps scale` |
| Per-request / per-CPU-second billing | Flat VPS cost |
| Multi-region front end | Single server |
| Secret Manager, Cloud SQL, Memorystore, … | PostgreSQL, MySQL, Redis, S3/MinIO — and growing |

Hop3 is simpler. You manage one server instead of a serverless platform wired into half a dozen other Google Cloud products.

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

## Step 2: Export Your Cloud Run Configuration

The fastest way to see exactly what your service runs with is to export its current revision as a Knative manifest:

```bash
gcloud run services describe your-app --region europe-west1 --format export > service.yaml
```

That file lists the image, the env vars, the resource limits, the concurrency, and any Secret Manager and Cloud SQL references. Plain env vars are visible in it; secret *values* are not — Cloud Run stores those as references into Secret Manager, so you'll see the secret name, not its contents. Pull the actual values from Secret Manager (or wherever you originally got them):

```bash
gcloud secrets versions access latest --secret=your-secret-name
```

Then plan to remove the entries Hop3 sets for you, and the ones that have no meaning off Cloud Run:

- `DATABASE_URL` (will be set by the Hop3 Postgres addon)
- `REDIS_URL` (will be set by the Hop3 Redis addon)
- `PORT` (Cloud Run injects it; so does Hop3 — let the platform set it)
- The Cloud SQL connector socket path (e.g. `/cloudsql/PROJECT:REGION:INSTANCE`) — there's no connector on Hop3; you connect over a normal host/port

## Step 3: Add hop3.toml

Here's where the concept mapping gets concrete. A representative Cloud Run `service.yaml` for a containerised web app with an env var, a Secret Manager reference, and a Cloud SQL instance looks roughly like this (trimmed):

```yaml
# service.yaml (Knative export, trimmed)
apiVersion: serving.knative.dev/v1
kind: Service
metadata:
  name: your-app
spec:
  template:
    metadata:
      annotations:
        run.googleapis.com/cloudsql-instances: my-project:europe-west1:your-app-db
        autoscaling.knative.dev/maxScale: "10"
    spec:
      containerConcurrency: 80
      containers:
        - image: gcr.io/my-project/your-app:latest
          ports:
            - containerPort: 8080
          env:
            - name: DJANGO_SETTINGS_MODULE
              value: myapp.settings.production
            - name: SECRET_KEY
              valueFrom:
                secretKeyRef:
                  name: your-secret-key
                  key: latest
          resources:
            limits:
              cpu: "1"
              memory: 512Mi
```

The same service as `hop3.toml`:

```toml
[metadata]
id = "your-app"

[build]
builder = "docker"

[env]
DJANGO_SETTINGS_MODULE = "myapp.settings.production"
# SECRET_KEY came from Secret Manager — re-set the value here,
# or out of band with `hop3 env set` so it never touches the repo.
SECRET_KEY = "your-secret-key-value"

[run]
before-run = ["python manage.py migrate"]

[healthcheck]
path = "/health/"

[limits]
memory = "512M"
cpu = 1
```

A few things changed, and each one is a Cloud Run primitive landing on a Hop3 one:

- **`metadata.name` → `[metadata].id`.** Same canonical name; the server uses it as the app's identity.
- **The container image maps to `[build] builder = "docker"`.** Hop3 builds the same `Dockerfile` (or rebuilds the same image) you shipped to Cloud Run. You don't push to a registry — Hop3 builds from your source on the server. (See the next section if you'd rather drop the container entirely.)
- **`containerPort: 8080` → bind `$PORT`.** Cloud Run already told your app to listen on `$PORT`, and so does Hop3: it assigns a dynamic `$PORT`, sets it in the environment, and the reverse proxy routes to it by hostname. If your container already reads `$PORT` (the Cloud Run convention), there's nothing to change.
- **Plain `env` entries → `[env]`.** Straight copy.
- **`secretKeyRef` (Secret Manager) → `[env]` or `hop3 env set`.** There's no separate secret store to wire up; Hop3 stores env values encrypted at rest in its database. Resolve the Secret Manager reference to its value and set it like any other variable (keep it out of the repo with `hop3 env set` if you'd rather not commit it).
- **`cloudsql-instances` annotation → a Hop3 addon (or an external URL).** The Cloud SQL connector disappears. Either attach a Hop3 Postgres addon (Step 4) and let it inject `DATABASE_URL`, or keep your existing Cloud SQL instance and point `[env]` at its URL (see "Keeping an External Managed Database").
- **`resources.limits` → `[limits]`.** Same idea: a memory and CPU cap. One caveat — `[limits]` is enforced for the Docker builder (it maps to the container's `mem_limit` / `cpus`); on a native or Nix build the cap isn't enforced yet, so declaring `[limits]` there aborts the deploy with a clear message rather than silently ignoring it.
- **`containerConcurrency` and `maxScale` simply disappear.** There's no per-request autoscaler to configure. Concurrency and instance count become a fixed number of uWSGI workers on one host — see "Concurrency and Scaling" below. These two lines are the most visible thing you lose, and the whole point of the trade-off.

## Step 4: Migrate Your Database

### Export from Cloud SQL

Cloud SQL is a managed Postgres (or MySQL), so you dump it the ordinary way. Connect through the Cloud SQL Auth Proxy and use `pg_dump`:

```bash
cloud-sql-proxy my-project:europe-west1:your-app-db &
pg_dump "postgres://postgres:PASSWORD@127.0.0.1:5432/your_app" \
    -Fc -f latest.dump
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

On Cloud Run your service got a `*.run.app` URL for free, and you mapped a custom domain through Google. On Hop3 you point a record at your one server:

```
your-app.example.com  A  your-server-ip
```

Once Let's Encrypt is configured on the server, Hop3 requests a certificate for the domain at deploy time. Out of the box, a freshly installed server serves a self-signed certificate until you point it at an ACME provider.

## Common Migration Issues

### Container vs Native Toolchains

Cloud Run always runs a container — an image you built from a Dockerfile, or one a buildpack produced for you. Hop3 can do the same with `[build] builder = "docker"`, so the simplest migration keeps your Dockerfile unchanged and just rebuilds it on the server.

But you often don't need it. Hop3 auto-detects a native toolchain from the files in your repo — Python, Node.js, Go, Ruby, Rust, Java, PHP, Elixir, .NET — and builds without a container at all. If your Dockerfile was just "install the runtime, copy the code, run the server", you can usually delete it and let Hop3 detect the language:

```toml
[build]
toolchain = "python"
```

For a multi-language build (say, Python plus a Node asset step), use `before-build`:

```toml
[build]
toolchain = "python"
before-build = "npm install && npm run build"
```

Keep `builder = "docker"` when your image does something Hop3's toolchains don't — a system package, a compiled C extension with awkward deps, a pinned runtime version. There's also a Nix builder and a static-site builder for the cases in between.

### Concurrency and Scaling

This is the part of Cloud Run that doesn't have a one-to-one replacement, so it's worth being plain about. On Cloud Run, `containerConcurrency` sets how many requests one instance handles at once, and the autoscaler adds and removes instances (down to zero) based on load. Hop3 has neither knob. Instead, you run a fixed number of worker processes on one server, and you set that number yourself:

```bash
hop3 ps scale your-app web=4
```

Four web workers handle requests concurrently, always on, with no cold start and no autoscaler. There's no scale-to-zero — the workers stay warm whether or not anyone is hitting the service — and there's no automatic scale-up under a spike. If load grows, you raise the worker count (or the size of the box) by hand. For a steady workload that's a feature: predictable capacity, predictable cost. For a bursty one, it's the trade-off you're accepting in return for no cold starts and a flat bill.

### Secrets (Secret Manager)

Cloud Run resolves Secret Manager references at instance start and injects them into the environment. Hop3's `[env]` is the same idea at the destination — values are stored encrypted at rest in Hop3's database — so secrets land in `[env]` in `hop3.toml`, or you set them out of band so they never touch the repo:

```bash
hop3 env set --app your-app SECRET_KEY=… STRIPE_KEY=…
hop3 app restart your-app
```

There's no separate secret-store product to provision and grant IAM access to; the env var *is* the secret, encrypted where it lives. Database and cache credentials are a special case: you don't copy them over at all. When you attach an addon, Hop3 injects `DATABASE_URL`, `REDIS_URL`, and friends for you, so drop those from your list entirely.

### Keeping an External Managed Database

Maybe you're moving the app off Cloud Run but you're not ready to move Cloud SQL — it's backed up, it's tuned, and migrating data is a separate project. You don't have to move it. Skip the addon and point `[env]` at the existing instance:

```toml
[env]
DATABASE_URL = "postgresql://user:pass@PUBLIC_IP:5432/mydb"
```

You'll need to enable a public IP (or another reachable path) on the Cloud SQL instance and allow your Hop3 server's address, since there's no Cloud SQL connector doing the networking for you anymore. Hop3 won't manage that database, but your app talks to it exactly as before. You can adopt a Hop3 addon later, when you're ready to cut the cord.

### Postgres Extensions

If your app relies on a Postgres extension (`pg_stat_statements`, `pgcrypto`, …), enable it on the Hop3 addon without SSH or manual `psql`:

```bash
hop3 addon postgres extensions your-app-db pg_stat_statements
```

Extensions are allow-listed, so only the ones Hop3 ships support for will install.

### Persistent Files

Cloud Run's filesystem is ephemeral — anything an instance writes vanishes when it's recycled, which is why you put uploads in Cloud Storage. Hop3's source tree is also replaced on each deploy, but you can declare a directory that survives redeploys with `[[volumes]]`:

```toml
[[volumes]]
name = "uploads"
target = "data/uploads"
```

Storage lives under the app's data root, outside the source tree that gets replaced on each deploy. If you were already using Cloud Storage and want object storage rather than a local directory, Hop3 has an S3/MinIO addon — attach it and point your app's S3 client at the injected `S3_*` variables.

### Scheduled Jobs (Cloud Scheduler)

On Cloud Run you typically ran periodic work with Cloud Scheduler hitting an endpoint, or a separate Cloud Run Job. In Hop3, declare a worker in `hop3.toml`:

```toml
[run.workers]
scheduler = "celery -A myapp beat"
```

Or use system cron on the one box:

```bash
ssh root@your-server.com
crontab -e
# Add: 0 * * * * /home/hop3/apps/your-app/venv/bin/python /home/hop3/apps/your-app/src/manage.py cleanup
```

### Cold Starts

There's nothing to migrate here — it's a gap that closes itself. Cloud Run's cold start is the price of scale-to-zero: the first request after an idle period waits for an instance (and your container) to come up. Hop3 keeps the process warm permanently, so there's no first-request penalty. The flip side is that you're paying for that warm process whether or not it's being used — which is exactly the bargain you're making.

### Multi-Region

Cloud Run can run the same service in several regions behind a global load balancer. Hop3 runs on one server. There's no multi-region, no global front end, no edge. Pick the region closest to your users, put the server there, and accept the latency for everyone else. The flip side is data locality: everything lives in one place you chose, which for a lot of apps (and a lot of compliance regimes) is the feature, not the limitation.

## Command Mapping

| Cloud Run Command | Hop3 Command |
|-------------------|--------------|
| `gcloud run deploy` (first time) | `hop3 app create` + `git push hop3 main` |
| `gcloud run services list` | `hop3 app list` |
| `gcloud run services describe` | `hop3 app status --app X` |
| `gcloud run services describe` (env) | `hop3 env show --app X` |
| `gcloud run services update --set-env-vars` | `hop3 env set K=V --app X` |
| `gcloud run services logs read` | `hop3 app logs --app X` |
| `gcloud run services describe` (instances) | `hop3 ps --app X` |
| `--min-instances` / `--max-instances` | `hop3 ps scale --app X web=N` |
| redeploy a revision | `hop3 app restart --app X` |
| `gcloud run jobs execute` (one-off) | `hop3 app run --app X` |
| Cloud SQL instance | `hop3 addon create postgres <name>` + `hop3 addon attach <name> --app X` |
| domain mapping | `hop3 domain add <host> --app X` |

## Cost and Lock-In

Cloud Run's pricing is per-request, per-CPU-second, and per-GiB-second of memory, with a free tier and then metered usage on top — plus whatever Cloud SQL, Secret Manager, and egress add. For a genuinely spiky service that's idle half the day, that can be very cheap. For an always-on service, you're paying serverless rates for a container that never scales to zero, and the bill moves with traffic in ways that are hard to predict. Hop3's bill doesn't move: you rent a VPS, you know the number, and adding traffic or a second app doesn't change it.

| | Cloud Run | Hop3 (self-hosted) |
|-|-----------|-------------------|
| Compute | per-request + per-CPU/memory-second | fixed VPS |
| Database | Cloud SQL (per-instance + storage) | included on the VPS |
| Secrets | Secret Manager (per-secret + access) | `[env]`, encrypted, included |
| Egress | metered | included (VPS allowance) |
| **Spiky app** | can be very cheap (scales to zero) | flat (no scale-to-zero) |
| **Always-on app** | serverless rates, climbs with traffic | ~$10–30/month (VPS) |

The lock-in angle is the quieter win. On Cloud Run your service is shaped around an image in Artifact Registry, Secret Manager references, a Cloud SQL connector, IAM bindings, and a Knative manifest. On Hop3 it's a Dockerfile (or a plain native build), env vars you own, a Postgres you can `pg_dump`, and a config file in your repo — nothing that only one vendor can run. Because you were already shipping a container, you arrive at Hop3 with the artifact you need and almost nothing to rewrite. If you ever leave Hop3 too, you leave with a standard app, not a platform-shaped one. The trade-off is the obvious one: you manage the server, but you control everything on it.

## Rollback Plan

Keep your Cloud Run service running during migration — a revision you don't touch keeps serving:

1. Deploy to Hop3 with a test domain (or a subdomain of your own)
2. Verify everything works against real data
3. Switch DNS to point at your Hop3 server
4. Keep the Cloud Run service running for 1–2 weeks
5. Run `gcloud run services delete your-app` (and tear down Cloud SQL / Secret Manager) once you're confident

Because DNS is the only switch, rollback is just pointing the record back at Cloud Run's domain mapping — no data has to move twice.

## Getting Help

- [Hop3 Documentation](https://hop3.cloud)
- [GitHub Issues](https://github.com/abilian/hop3/issues)
- [Troubleshooting Guide](/guides/troubleshooting/)

---

*Coming from a different platform? The concepts are similar. Check the [Getting Started guide](/get-started/) for a fresh start.*
