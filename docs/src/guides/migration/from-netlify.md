# Migrating from Netlify to Hop3

Thinking about leaving Netlify? Maybe build minutes and bandwidth overages have made your bill unpredictable, maybe a client needs the whole site to live on infrastructure they control, or maybe the serverless model has started to fight you — cold starts, function timeouts, a stateful job that doesn't want to be stateless. Hop3 lets you keep a static front end and pair it with a real, always-on backend on a server you own. This guide helps you migrate a Netlify project to Hop3.

A caveat up front, because it shapes everything below: this is a **partial fit**, not a drop-in. Netlify is a global CDN with serverless functions, deploy previews, Forms, and Edge Functions. Hop3 is a single origin server. The static side maps cleanly; the platform-managed pieces (CDN, previews, Forms, edge) either change shape or have no direct equivalent. We'll be explicit about each one as we go, rather than pretend the gap isn't there.

## What's Similar

The static-build half of Netlify maps almost one-to-one onto Hop3's static builder, and your config concepts carry over:

| Netlify | Hop3 |
|---------|------|
| `netlify.toml` `[build].command` | `[build].build` in `hop3.toml` |
| `[build].publish` (publish dir) | `[build].static-dir` |
| `[build.environment]` | `[env]` |
| Custom domain | `hop3 domain add` + ACME |
| Simple `_redirects` rules | Hop3's generated nginx |

A static site on Hop3 is served straight from disk by nginx — no app process, no Procfile. You point Hop3 at the directory your build emits and it serves it.

One syntactic note: Hop3's CLI uses spaces, and the app you're targeting is always the `--app` flag rather than a positional argument. So where you'd run a Netlify CLI command against a site, on Hop3 you write, e.g., `hop3 env set FOO=bar --app myapp`.

## What's Different

| Netlify | Hop3 |
|---------|------|
| Global CDN / edge network | Single origin server (no CDN, no edge) |
| Serverless Functions | A regular always-on backend process |
| Deploy previews per PR | Deploy a separate staging app manually |
| Forms | No direct equivalent |
| Edge Functions | No direct equivalent |
| Per-build / bandwidth metering | A flat VPS bill |
| Many integrations | PostgreSQL, MySQL, Redis, S3/MinIO — and growing |

Read the left column carefully before you commit. The biggest change is architectural: **Netlify Functions stop being serverless**. On Hop3 they become a small backend app — a Node or Python process that runs all the time, behind nginx, on the same server as your static files. That's a feature if you wanted persistent connections, background work, or a real database next to your code; it's a regression if you were leaning on serverless's scale-to-zero billing.

And two Netlify features have **no direct Hop3 equivalent**: Forms (Netlify's built-in form capture) and Edge Functions (code that runs at CDN edge locations). If your site depends on either, you'll need to build the equivalent yourself — a form-handling endpoint in your backend app for the former, and there is simply no edge tier for the latter. Say this out loud to stakeholders early.

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

## Step 2: Inventory Your Netlify Project

Open your `netlify.toml` (and the Netlify dashboard) and write down four things:

- **Build command and publish directory** — e.g. `command = "npm run build"`, `publish = "dist"`. These become `[build].build` and `[build].static-dir`.
- **Environment variables** — the build-time and runtime vars from `[build.environment]` and the dashboard. These become `[env]`. Drop anything Netlify-specific (`NETLIFY`, `DEPLOY_*`, `CONTEXT`, `URL`, build-image vars).
- **Functions** — every file under your functions directory. Each is a handler you'll fold into a single always-on backend app (Step 4).
- **Redirects and headers** — your `_redirects` file and `[[redirects]]` / `[[headers]]` blocks. Simple host/path redirects map to Hop3's generated nginx; anything proxy-like or rule-heavy may need a hand-written nginx snippet.

There is no automated importer for `netlify.toml`. Hop3's only config importer is `hop3 app migrate procfile <dir>`, which converts a `Procfile` into a `hop3.toml`. Everything else — `netlify.toml`, `_redirects`, function wiring — is translated **by hand**. The mappings in this post are that translation; there is no `import` or `convert` command to invent here.

## Step 3: Add hop3.toml — the Static Front End

For a purely static site (or the static half of a Jamstack project), the translation is small. Suppose your `netlify.toml` looks like this:

```toml
# netlify.toml
[build]
  command = "npm run build"
  publish = "dist"

[build.environment]
  NODE_VERSION = "20"
  API_BASE = "https://api.example.com"
```

The Hop3 equivalent:

```toml
# hop3.toml
[metadata]
id = "your-site"

[build]
toolchain = "static"
build = "npm run build"
static-dir = "dist"        # the directory your build emits — Netlify's "publish"

[env]
API_BASE = "https://api.example.com"

[domains]
list = ["your-site.example.com"]
```

That's a complete static deployment: Hop3 runs your build command, then nginx serves `dist/` directly — no app process. If you don't declare `static-dir`, it defaults to `public`.

**Redirects.** Plain redirects (one host or path to another) are handled by the nginx config Hop3 generates from your domains. Netlify's richer `_redirects` syntax — splat/placeholder rewrites, proxying to an upstream, status-code rules, role-based rules — has no one-to-one mapping. For those, drop a hand-written nginx snippet on the server. Treat that as a sign you've outgrown the "purely static" path and probably want a backend app in front of the rules anyway.

A purely static site works well on Hop3 — but be clear-eyed about the trade: **you lose the CDN**. Your files are served from one origin in one region, not from a global edge network. For many sites that's fine (and you can always put a CDN of your choosing in front of the origin later); for a latency-sensitive global audience, it's the cost of owning the box.

## Step 4: Turn Functions Into a Backend App

This is the heart of the migration. Netlify Functions are serverless handlers; Hop3 has no serverless tier. The move is to collect your functions into **one small always-on backend app** — an Express/Fastify server in Node, or a Flask/FastAPI app in Python — where each former function becomes a route. Hop3 runs that process behind nginx and keeps it alive.

Concretely, a function that lived at `/.netlify/functions/subscribe` becomes a route like `POST /api/subscribe` in your backend, and your front end calls `/api/subscribe` instead.

Give the backend its own `hop3.toml`. Hop3 auto-detects the toolchain (Node.js, Python, Go, Ruby, Rust, Java, PHP, Elixir, .NET), so a minimal Node backend needs very little:

```toml
# hop3.toml  (backend app)
[metadata]
id = "your-site-api"

[env]
NODE_ENV = "production"

[run]
before-run = ["npm run db:migrate"]

[healthcheck]
path = "/api/health"
timeout = 5
retries = 3
```

Hop3 reads the process model from your `Procfile` if you have one (`web: node server.js`), or you can declare it in `hop3.toml`. The app listens on the `$PORT` Hop3 assigns and Hop3 proxies it.

You now have two apps: a static `your-site` and a backend `your-site-api`. Point the front end at the backend's URL (via `[env]`), or bind them to subdomains of the same domain. There's no serverless cold start — the backend is always running — which is exactly the property that makes persistent connections and a colocated database possible.

If you only have a couple of functions and they're light, you can also fold them straight into a single Node/Python app that both builds the static assets *and* serves the API, deployed as one Hop3 app. Two apps is cleaner for separation; one app is simpler to operate. Either is fine.

## Step 5: Add a Database or Other Addons

Netlify pushes you toward external data services. On Hop3 you can run the data layer on the same server. Hop3 ships four addon types — **PostgreSQL, MySQL, Redis, and S3/MinIO** (and growing). There's no managed MongoDB or hosted queue; if your stack needs one of those, keep using your existing managed service and point `[env]` at its URL (see the end of this step).

Create the database addon and attach it to the backend app:

```bash
hop3 addon create postgres your-site-db
hop3 addon attach your-site-db --app your-site-api
```

Get the connection details (the addon injects `DATABASE_URL` into the app automatically):

```bash
hop3 addon show your-site-db
```

If your app needs Postgres extensions, enable them through the addon command — no SSH or manual `psql`:

```bash
hop3 addon postgres extensions your-site-db pgcrypto
```

Extensions are allow-listed, so only the ones Hop3 ships support for will install.

**Keeping an external managed database.** Migrating off Netlify doesn't force you to move your data too. If you'd rather keep your existing managed Postgres (or a service Hop3 doesn't offer, like MongoDB), skip the addon and point the app at the external URL:

```toml
[env]
DATABASE_URL = "postgresql://user:pass@db.your-provider.com:5432/yourdb"
```

For secrets you'd rather not commit, set them with `hop3 env set --app your-site-api DATABASE_URL=...` instead of putting them in `hop3.toml`.

## Step 6: Deploy to Hop3

Add Hop3 as a git remote and push, the same shape as `git push` to any PaaS:

```bash
git remote add hop3 hop3@your-server.com:your-site
git push hop3 main
```

(`hop3 deploy` does the same thing by uploading your working tree, if you'd rather not go through git.)

Deploy the backend app the same way from its own repo or directory.

## Step 7: Point Your Domain

Update your DNS to point at the server:

```
your-site.example.com  A  your-server-ip
```

Then bind the hostname to the app:

```bash
hop3 domain add your-site.example.com --app your-site
```

Once Let's Encrypt / ACME is configured on the server, Hop3 requests a real certificate for the domain at deploy time. Out of the box, a freshly installed server serves a self-signed certificate until you point it at an ACME provider.

## Common Migration Issues

### Build environment and Node version

Netlify pins a build image and a `NODE_VERSION`. Hop3 builds with the toolchain it detects on the server. If you need a specific Node or Python version that the host doesn't provide, use the Docker builder and control the version in your Dockerfile:

```toml
[build]
builder = "docker"
```

The Docker builder also enforces `[limits]` (memory/CPU), which native builds don't yet.

### Deploy previews

Netlify spins up a preview URL for every pull request. Hop3 has no built-in preview-per-PR mechanism. The workaround is the same as on other single-server PaaSes: deploy a **separate staging app** by hand and treat it as your preview environment.

```bash
hop3 app create your-site-staging
git push hop3-staging feature-branch:main
```

Bind it to a staging subdomain and you have a stable place to review changes — just not one that appears automatically per PR.

### Forms

Netlify Forms (the `netlify` form attribute that captures submissions for you) has no Hop3 equivalent. If your site uses it, add a form-handling route to your backend app (Step 4): accept the POST, validate, store it in your database or email it. It's a small endpoint, but it's code you now own rather than a platform feature.

### Edge Functions

Netlify Edge Functions run at CDN edge locations, close to the user. Hop3 has no edge tier — there is one origin server. Logic that lived in an Edge Function moves into your origin backend app and runs there. You lose the edge-proximity latency benefit; there's no way around that on a single-server platform, so plan for it rather than discover it.

### Scheduled functions

Netlify Scheduled Functions don't exist on Hop3. Use a worker process in your backend app, or system cron on the server:

```bash
ssh root@your-server.com
crontab -e
# Add: 0 * * * * curl -fsS http://127.0.0.1:PORT/api/cron/cleanup
```

## Command and Concept Mapping

| Netlify concept | Hop3 |
|-----------------|------|
| `netlify.toml` `[build].command` | `[build].build` |
| `netlify.toml` `[build].publish` | `[build].static-dir` |
| `[build.environment]` | `[env]` (or `hop3 env set --app X`) |
| Site env vars | `hop3 env show --app X` / `hop3 env set K=V --app X` |
| Functions | A backend app (route per function) |
| Custom domain | `hop3 domain add <host> --app X` |
| `_redirects` (simple) | Generated nginx |
| `_redirects` (complex) | Hand-written nginx snippet |
| Forms | Backend route (build it yourself) |
| Edge Functions | Origin backend (no edge tier) |
| Deploy preview | Manual staging app + `ps scale` |
| Scale a process | `hop3 ps scale --app X web=N` (manual) |
| One-off task | `hop3 app run --app X <cmd>` |
| Logs | `hop3 app logs --app X` |
| Restart | `hop3 app restart --app X` |
| Database / cache | `hop3 addon create <type> <name>` + `addon attach` |

A few things deliberately aren't in that table because Hop3 doesn't have them: no global CDN, no edge runtime, no autoscaling (scaling is manual via `hop3 ps scale`), no built-in form capture, no per-PR preview automation, and a single server rather than a multi-region fleet.

## Cost and Lock-In

Netlify's pricing is metered: build minutes, bandwidth, function invocations, and overages on each. That's predictable until a traffic spike or a chatty function makes it not. Hop3 runs on a VPS you rent — a small site fits comfortably on a ~$10/month box, a heavier one on ~$30/month — and the bill is flat regardless of how much you build or how much traffic you serve, up to the machine's capacity.

The deeper difference is lock-in. Netlify Functions, Forms, and Edge Functions are platform-shaped: leaving means rewriting them. On Hop3 your backend is an ordinary Node or Python app behind nginx, your data is in a Postgres you can `pg_dump`, and your config is a `hop3.toml` you can read. If you ever leave Hop3 too, you're leaving with a normal app and a normal database — not with a pile of vendor-specific handlers to unwind.

The trade-off is symmetric: you give up the CDN, the edge, deploy previews, and zero-ops scaling, and in return you get a flat bill, data residency, and a stack with no proprietary surface.

## Rollback Plan

Keep your Netlify site live during the migration — nothing here requires switching DNS before you're ready:

1. Deploy the static app and the backend app to Hop3 on a temporary subdomain.
2. Verify the site renders, the API routes answer, and the database round-trips.
3. Switch DNS for the real domain to the Hop3 server and let `hop3 domain add` + ACME issue the certificate.
4. Keep the Netlify site running for 1–2 weeks as a fallback.
5. Tear down the Netlify site once you're confident.

Because the cutover is just a DNS change, rolling *back* is also just a DNS change: point the record at Netlify again while you investigate.

## Getting Help

- [Hop3 Documentation](https://hop3.cloud)
- [GitHub Issues](https://github.com/abilian/hop3/issues)

---

*Coming from a different platform? The concepts are similar. Check the [Getting Started guide](/get-started/) for a fresh start.*
