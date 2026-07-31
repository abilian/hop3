# Migrating from Vercel to Hop3

Thinking about moving a Next.js app off Vercel? Maybe you want predictable flat-rate costs instead of per-invocation and bandwidth billing, no cold starts on a low-traffic route, or data that lives on infrastructure you control. Hop3 runs your full-stack Next.js app as a single always-on Node process on your own server. This guide helps you migrate an existing Vercel project to Hop3 — and is clear about where the two platforms differ.

## Is Hop3 a Good Fit?

Read this section first. Vercel and Hop3 have different shapes, and the migration is smooth only when your app fits.

Hop3 is a single always-on server. It runs your Next.js app as one long-lived Node process (`next start`, or the standalone server), behind a reverse proxy, on a box you provision. That is the ideal target for a **server-rendered / full-stack Next.js app**: SSR pages, API routes, and server actions all served by that one process.

It is **not** a fit for an app built around edge functions or heavy serverless fan-out:

- **No global edge / CDN.** Hop3 is a single origin server in one region. Vercel's global edge network has no Hop3 equivalent — you serve from one place.
- **No per-function autoscaling.** Each route does not scale independently. You scale the whole process, manually, with `hop3 ps scale`.
- **No managed preview deployments.** There are no per-PR review apps. You run a separate staging app instead.
- **A purely static site works, but loses the CDN.** Hop3 has a static-site builder, so a fully static export deploys fine — you just serve it from your one origin instead of Vercel's CDN.

If your app leans on the edge runtime, on serverless functions scaling to zero and back, or on a worldwide CDN as a core feature, Hop3 is the wrong tool — stay where you are. If your Next.js app is really a web server that happens to be deployed serverless, read on.

## What's Similar

The day-to-day workflow will feel familiar:

| Vercel | Hop3 |
|--------|------|
| `git push` (Git-connected deploy) | `git push hop3 main` |
| Project environment variables | `[env]` in `hop3.toml` / `hop3 env set` |
| Vercel Postgres / KV / Blob | `hop3 addon` (postgres / redis / s3) |
| Custom domains | `hop3 domain add` + ACME |
| Build & output settings | `[build]` in `hop3.toml` |

Your Next.js source doesn't change. You point a Git remote at your server and push, and Hop3 builds and runs it.

One thing to internalize up front: on Hop3 the app you're targeting is always the `--app` flag, never a positional argument. So a command reads `hop3 env set FOO=bar --app myapp`.

## What's Different

| Vercel | Hop3 |
|--------|------|
| Managed platform | Self-hosted |
| Serverless / edge functions | One always-on Node process |
| Global edge network + CDN | Single origin server, one region |
| Per-function autoscaling | Manual scaling (`hop3 ps scale`) |
| Preview deployments per PR | Not supported — use a staging app |
| Vercel Postgres / KV / Blob | PostgreSQL, MySQL, Redis, S3/MinIO — and growing |

Hop3 is simpler in operation: one server, one process, one bill. You give up the edge and the magic; you get always-on behavior, flat cost, and control.

## How the Concepts Map

The migration is mostly a translation of Vercel primitives to Hop3 ones. Here's the concrete mapping:

| Vercel primitive | On Hop3 |
|------------------|---------|
| The Next.js app | Node toolchain runs `next build`, then `next start` (or the standalone server) as the long-lived `web` process |
| API routes / server actions | Served by that **same** Node process — not split into separate serverless functions |
| Edge functions | No equivalent — must run in the Node process (or stay on Vercel) |
| Environment variables | `[env]` in `hop3.toml` (note: `NEXT_PUBLIC_*` are build-time / public) |
| Vercel Postgres | `hop3 addon create postgres …` |
| Vercel KV | `hop3 addon create redis …` |
| Vercel Blob | `hop3 addon create s3 …` |
| Vercel Cron | `[run.workers]` or system cron |
| Custom domain | `hop3 domain add` + a real certificate once ACME is configured |

The key shift is the second row: on Vercel your API routes become independent serverless functions; on Hop3 they're handled by the one Node server that also renders your pages. For a full-stack app that's usually exactly what you want — no cold starts, shared in-memory state, one place to reason about.

We recommend Next.js **standalone output mode** for the Hop3 target. It produces a minimal, self-contained production server (`.next/standalone/server.js`) that's ideal for running as one long-lived process. Hop3 has a full [Next.js tutorial](https://hop3.cloud) covering this end to end.

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

## Step 2: Export Your Vercel Configuration

Pull your environment variables from Vercel using their CLI:

```bash
vercel env pull .env.vercel
```

Review the file. A few things to keep in mind as you translate it:

- `NEXT_PUBLIC_*` variables are **build-time and public** — they get inlined into the client bundle at build. Keep them, but never put a secret behind a `NEXT_PUBLIC_` name.
- Drop the connection strings Vercel managed for you (`POSTGRES_URL`, `KV_URL`, `BLOB_READ_WRITE_TOKEN`, …) — Hop3 addons set their own (`DATABASE_URL`, `REDIS_URL`, `S3_*`).
- Drop anything Vercel injected automatically (`VERCEL`, `VERCEL_URL`, `VERCEL_ENV`, …). The port is auto-set by Hop3 as `$PORT`.

## Step 3: Add hop3.toml

This is where you translate Vercel's project settings — build command, output, env vars, runtime — into one file. A representative full-stack Next.js app (standalone output) looks like this:

```toml
[metadata]
id = "your-app"

[build]
toolchain = "node"
before-build = "npm ci && npm run build"

[run]
start = "node .next/standalone/server.js"
before-run = "cp -r .next/static .next/standalone/.next/ && cp -r public .next/standalone/ 2>/dev/null || true"

[env]
NODE_ENV = "production"
# Public, build-time — inlined into the client bundle:
NEXT_PUBLIC_API_URL = "https://your-app.example.com"
# Server-only secrets:
SECRET_KEY = "your-secret-key"

[healthcheck]
path = "/"
```

A couple of notes on the translation:

- `next build` runs in `before-build`; the standalone server runs as the `web` process via `[run].start`. The `before-run` line copies the static assets next to the standalone server (Next.js standalone output doesn't bundle them by default).
- A `Procfile` is also supported if you prefer it for the process model — the `web:`, `prebuild:`, and `prerun:` lines map onto the same fields.
- If you'd rather pin the toolchain and dependency stack precisely, Hop3 also offers a Docker builder (`[build] builder = "docker"`) and a Nix builder.

## Step 4: Migrate Your Data

This is the part that takes the most care, because Vercel's managed storage maps onto three different Hop3 addons.

The four addon types Hop3 offers are **PostgreSQL, MySQL, Redis, and S3/MinIO** (and growing). That covers the common Vercel storage triad:

| Vercel | Hop3 addon |
|--------|------------|
| Vercel Postgres | `postgres` |
| Vercel KV | `redis` |
| Vercel Blob | `s3` |

### Postgres (Vercel Postgres → Hop3 postgres)

Vercel Postgres is Postgres under the hood, so a standard dump-and-restore works. Dump from your Vercel database using the connection string from the dashboard:

```bash
pg_dump "$POSTGRES_URL" -Fc -f latest.dump
```

Create the addon and attach it to your app:

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

If your schema needs a Postgres extension (`pgvector`, `pg_stat_statements`, …), enable it through the addon command — no manual `psql` needed:

```bash
hop3 addon postgres extensions your-app-db pgvector
```

Extensions are allow-listed, so only the ones Hop3 ships support for will install.

Once attached, the addon injects `DATABASE_URL` into your app's environment — point your code at that instead of `POSTGRES_URL`.

### KV (Vercel KV → Hop3 redis)

Vercel KV is Redis-compatible. Create a Redis addon and attach it:

```bash
hop3 addon create redis your-app-cache
hop3 addon attach your-app-cache --app your-app
```

It injects `REDIS_URL`. Most KV usage is cache, so starting fresh is usually fine — if you need to carry data over, export it from your KV instance and load it into the addon.

### Blob (Vercel Blob → Hop3 s3)

Vercel Blob maps to Hop3's S3/MinIO addon:

```bash
hop3 addon create s3 your-app-blobs
hop3 addon attach your-app-blobs --app your-app
```

It injects `S3_*` connection variables. Copy your existing blobs into the new bucket (e.g. with `rclone` or the `aws s3` CLI pointed at both endpoints), then update your code to read the `S3_*` vars.

### Keeping an external managed database

You don't have to move the data at all. If you'd rather keep an existing managed Postgres (Neon, RDS, your current Vercel Postgres), just point `[env]` at its URL and skip the addon:

```toml
[env]
DATABASE_URL = "postgresql://user:pass@db.example.com:5432/your_app"
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

Hop3 detects the Node toolchain, runs your `before-build` (`next build`), and starts the standalone server as the `web` process.

## Step 6: Point Your Domain

Add the hostname to your app, then update DNS:

```bash
hop3 domain add your-app.example.com --app your-app
```

```
your-app.example.com  A  your-server-ip
```

Once Let's Encrypt is configured on the server, Hop3 requests a certificate for the domain at deploy time. Out of the box, a freshly installed server serves a self-signed certificate until you point it at an ACME provider.

## Common Migration Issues

### Edge functions

If your app uses the edge runtime (middleware on the edge, `export const runtime = 'edge'`), those paths have no Hop3 equivalent — Hop3 runs one Node process, not an edge network. Move that logic into the Node runtime, or keep it on Vercel. There's no way to fake the edge on a single origin server, and we won't pretend otherwise.

### API routes and server actions

These need no change in your code — but understand what moved. On Vercel each route may run as its own serverless function; on Hop3 they all run inside the one Node process that also renders your pages. Long-running work that you relied on a separate function (and its own timeout) to handle should move to a worker (see below) rather than blocking a request.

### NEXT_PUBLIC_ variables

`NEXT_PUBLIC_*` values are read at **build time** and inlined into the client bundle. They live in `[env]` like any other variable, but changing one requires a rebuild (`git push hop3 main` again) to take effect — setting it with `hop3 env set` and restarting is not enough, because the value was baked into the bundle at build.

### Scheduled jobs (Vercel Cron)

Vercel Cron hits an endpoint on a schedule. On Hop3 you have two options.

A long-running worker process, declared alongside your `web` process:

```toml
[run.workers]
scheduler = "node scripts/scheduler.js"
```

Or system cron, if you just want to hit a route on a schedule the way Vercel Cron did:

```bash
ssh root@your-server.com
crontab -e
# Add: 0 * * * * curl -fsS https://your-app.example.com/api/cron/cleanup
```

### Preview deployments

Hop3 has no per-PR preview deployments. The workaround is a dedicated staging app:

1. Deploy a second app, e.g. `your-app-staging`, from your staging branch.
2. Or use branch-based names: `your-app-feature-x`.

Each is a real, separate Hop3 app — there is no automatic per-PR lifecycle.

### Scaling

There is no per-function or per-route autoscaling, and no automatic scaling at all. You scale the whole process manually:

```bash
hop3 ps scale --app your-app web=3
```

For a single-server full-stack app this is usually a deliberate, infrequent operation, not something the platform does for you under load.

## Command Mapping

| Vercel CLI | Hop3 Command |
|------------|--------------|
| `vercel` / `vercel deploy` | `git push hop3 main` or `hop3 deploy` |
| `vercel ls` / `vercel projects ls` | `hop3 app list` |
| `vercel inspect` | `hop3 app status --app X` |
| `vercel env ls` | `hop3 env show --app X` |
| `vercel env add` | `hop3 env set K=V --app X` |
| `vercel logs` | `hop3 app logs --app X` |
| `vercel logs` | `hop3 app logs --app X` |
| (Vercel storage dashboard) | `hop3 addon create` / `hop3 addon attach` |
| `vercel domains add` | `hop3 domain add <host> --app X` |
| (one-off task) | `hop3 app run --app X` |

> A note on importing config: Hop3's only config importer is `hop3 app migrate procfile <dir>`, which turns a `Procfile` into a `hop3.toml`. There is no importer for `vercel.json` — the build command, output mode, env, and cron settings are translated by hand, exactly as shown in Step 3. That's a small one-time cost, and the result is a single file you can read and version.

## Cost and Lock-In

Vercel's pricing is usage-based: function invocations, bandwidth, and managed-storage tiers. That's friendly at zero traffic and can spike unpredictably under load or with heavy bandwidth. Hop3 is a flat VPS bill — you pay for the box whether it serves one request or a million.

| | Vercel | Hop3 (self-hosted) |
|-|--------|-------------------|
| Compute | per-invocation + bandwidth | flat VPS (~$10–30/month) |
| Postgres / KV / Blob | metered managed tiers | included on your server (addons) |
| Cold starts | possible on idle routes | none (always-on process) |
| Bill predictability | varies with traffic | fixed |

Beyond cost, the angle is control: always-on behavior with no cold starts, a predictable monthly number, and data residency on infrastructure you own. The trade-off is real and worth restating — you run the server, you have one region, and you scale by hand. For a Next.js app that doesn't need the edge, that's a fair trade.

## Rollback Plan

Keep your Vercel project running during the migration:

1. Deploy to Hop3 on a test hostname (e.g. `your-app-new.example.com`).
2. Verify everything works — SSR pages, API routes, database, cron.
3. Switch DNS to point at your Hop3 server.
4. Keep the Vercel project live for 1–2 weeks.
5. Tear down the Vercel project once you're confident.

Because DNS is the only switch, rollback is just pointing the record back at Vercel.

## Getting Help

- [Hop3 Documentation](https://hop3.cloud)
- [Next.js on Hop3 tutorial](https://hop3.cloud)
- [GitHub Issues](https://github.com/abilian/hop3/issues)

---

*Coming from a different platform? The concepts are similar. Check the [Getting Started guide](/get-started/) for a fresh start.*
