# Migrating from Fly.io to Hop3

Thinking about leaving Fly.io? Maybe you spun up an app in three regions, watched the bill climb, and realised you only ever serve one continent. Maybe a Machine got stuck, or a cold start bit a request, or you just want the whole thing on one box you understand. Whatever the reason, Hop3 gives you a familiar `fly.toml`-shaped deployment on your own infrastructure. This guide helps you migrate existing Fly.io apps to Hop3.

The trade-off is worth stating up front, before you spend an afternoon on it. Fly.io is built for global distribution: anycast routing, Machines you can place in dozens of regions, an edge that puts your app close to users everywhere. Hop3 is a single server. You give up multi-region and per-Machine scaling, and in exchange you get one predictable bill, one place to look when something breaks, and your data living in exactly one jurisdiction you chose. If your app genuinely needs to be on five continents at once, stay on Fly. If it's a web app, a database, a couple of workers — and the regions were aspirational — Hop3 will feel like a relief.

## What's Similar

Hop3 was designed with the same deploy-from-a-config-file workflow Fly users already know:

| Fly.io | Hop3 |
|--------|------|
| `fly.toml` | `hop3.toml` |
| `flyctl deploy` | `git push hop3 main` (or `hop3 deploy`) |
| `fly secrets set` | `hop3 env set` |
| `fly postgres create` | `hop3 addon create postgres` |
| `fly logs` | `hop3 app logs` |

The shape is the same: one declarative file in your repo, one command to ship. Where Fly drives everything through `flyctl <noun> <verb>`, Hop3 uses space-separated `hop3 <noun> <verb>`, and the app you're targeting is always the `--app` flag rather than baked into the command's context. So `fly secrets set FOO=bar -a myapp` becomes `hop3 env set FOO=bar --app myapp`.

There's no automated `fly.toml` importer, but the translation is short and mechanical — the sections below walk through it field by field. (If your app keeps its process definitions in a `Procfile` rather than `fly.toml`'s `[processes]` block, `hop3 app migrate procfile . --dry-run` will scaffold a starting `hop3.toml` from that.)

## What's Different

| Fly.io | Hop3 |
|--------|------|
| Multi-region, anycast edge | Single server |
| Fly Machines (per-machine scaling) | Manual scaling on one host |
| Autoscaling | Manual via `hop3 ps scale` |
| Many managed services | PostgreSQL, MySQL, Redis, S3/MinIO — and growing |
| Private 6PN networking | Apps colocated on one host (localhost) |

Hop3 is simpler. You manage one server instead of a fleet of Machines spread across regions.

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

## Step 2: Export Your Fly.io Configuration

Your `fly.toml` is the obvious starting point — copy it somewhere handy. Your secrets are not in it (Fly keeps them encrypted and won't print values back), so list the names so you know what you'll need to re-set:

```bash
fly secrets list -a your-app
```

Fly only shows you the keys and a digest, never the values. Pull the actual values from wherever you originally got them — your password manager, your provider dashboards, the `.env` you deployed from. Then plan to remove Fly-specific entries that Hop3 sets for you:

- `DATABASE_URL` (will be set by the Hop3 Postgres addon)
- `REDIS_URL` (will be set by the Hop3 Redis addon)
- `PORT` (auto-set by Hop3)
- `FLY_*` variables (`FLY_APP_NAME`, `FLY_REGION`, `FLY_PUBLIC_IP`, …) — these have no meaning off Fly

## Step 3: Add hop3.toml

Here's where the concept mapping gets concrete. A representative `fly.toml` for a web app with a Dockerfile, a volume, and an internal port looks roughly like this:

```toml
# fly.toml
app = "your-app"
primary_region = "cdg"

[build]
  dockerfile = "Dockerfile"

[http_service]
  internal_port = 8080
  force_https = true

[[mounts]]
  source = "uploads"
  destination = "/app/uploads"

[checks.health]
  path = "/health/"
```

The same app as `hop3.toml`:

```toml
[metadata]
id = "your-app"

[build]
builder = "docker"

[env]
# From `fly secrets list` — re-set the values here, or via `hop3 env set`
SECRET_KEY = "your-secret-key"
DJANGO_SETTINGS_MODULE = "myapp.settings.production"

[run]
before-run = ["python manage.py migrate"]

[[volumes]]
name = "uploads"
target = "data/uploads"

[healthcheck]
path = "/health/"
```

A few things changed, and each one is a Fly primitive landing on a Hop3 one:

- **`app` → `[metadata].id`.** Same canonical name; the server uses it as the app's identity.
- **`primary_region` simply disappears.** There's one host, so there's nowhere to pin a region. That line is the most visible thing you lose — and the whole point of the trade-off.
- **The Dockerfile maps to `[build] builder = "docker"`.** Hop3 builds the same `Dockerfile` you shipped to Fly. (See the next section if you'd rather drop the Dockerfile entirely.)
- **`[http_service].internal_port` → bind `$PORT`.** Hop3 assigns a dynamic `$PORT`, sets it in the environment, and the reverse proxy routes to it by hostname. Make your app read `$PORT` instead of hardcoding `8080`. `force_https` has no equivalent toggle — Hop3 terminates TLS at the proxy and you point the domain at it (Step 6).
- **`[[mounts]]` → `[[volumes]]`.** Fly's `destination` is an absolute path; Hop3's `target` is a directory inside your app tree (relative, no `..`) that survives redeploys. Storage lives under the app's data root, outside the source tree that gets replaced on each deploy.
- **`[checks]` → `[healthcheck]`.** Same idea, single path.

## Step 4: Migrate Your Database

### Export from Fly

Fly Postgres is a Postgres you run on a Machine, so you dump it the ordinary way. Connect through a proxy and use `pg_dump`:

```bash
fly proxy 5432 -a your-app-db &
pg_dump "postgres://postgres:PASSWORD@localhost:5432/your_app" \
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

On Fly your app got an anycast IP and `*.fly.dev` for free. On Hop3 you point a record at your one server:

```
your-app.example.com  A  your-server-ip
```

Once Let's Encrypt is configured on the server, Hop3 requests a certificate for the domain at deploy time. Out of the box, a freshly installed server serves a self-signed certificate until you point it at an ACME provider.

## Common Migration Issues

### Dockerfile vs Native Toolchains

Fly always builds a container — a Dockerfile, or a buildpack that produces one. Hop3 can do the same with `[build] builder = "docker"`, so the simplest migration keeps your Dockerfile unchanged.

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

### Non-HTTP Services

If your Fly app exposed a raw TCP/UDP port (`[[services]]` with an `internal_port` that wasn't HTTP — SMTP, RTMP, a game server), that's not the HTTP path. HTTP apps use the dynamic `$PORT` and are proxied by hostname, so they never declare a port. A fixed host port is declared with `[[ports]]`:

```toml
[[ports]]
number = 1935
protocol = "tcp"
name = "rtmp"
```

Hop3 records each fixed port in a host-wide registry and refuses a second app that wants the same one — before it builds — so two apps can't silently fight over it. One caveat worth knowing up front: fixed ports are opened for native and Nix builds; a Docker-deployed app claims the port (so the conflict check works) but the firewall isn't opened for it yet. Use a native or Nix build for an app that needs a reachable fixed port.

### Secrets

`fly secrets` are encrypted at rest and injected into the Machine environment. Hop3's `[env]` is the same idea — values are stored encrypted in the database — so secrets land in `[env]` in `hop3.toml`, or you set them out of band so they never touch the repo:

```bash
hop3 env set --app your-app SECRET_KEY=… STRIPE_KEY=…
hop3 app restart your-app
```

Database and cache credentials are a special case: you don't copy them over at all. When you attach an addon, Hop3 injects `DATABASE_URL`, `REDIS_URL`, and friends for you, so drop those from your secrets list entirely.

### Keeping an External Managed Database

Maybe you ran Fly Postgres but your real database is a managed Postgres elsewhere (Neon, Crunchy, RDS) that you're not ready to move. You don't have to. Skip the addon and point `[env]` at the existing URL:

```toml
[env]
DATABASE_URL = "postgresql://user:pass@db.example.com:5432/mydb"
```

Hop3 won't manage that database, but your app talks to it exactly as before. You can adopt a Hop3 addon later.

### Postgres Extensions

If your app relies on a Postgres extension (`pg_stat_statements`, `pgcrypto`, …), enable it on the Hop3 addon without SSH or manual `psql`:

```bash
hop3 addon postgres extensions your-app-db pg_stat_statements
```

Extensions are allow-listed, so only the ones Hop3 ships support for will install.

### Redis Data

Most Redis on Fly is cache and doesn't need migrating — let it warm up fresh. If you do have data to keep, dump it from your Fly Redis and load it into the Hop3 addon:

```bash
# Or just start fresh — most Redis data is cache
hop3 addon redis import your-app-cache --confirm=your-app-cache < dump.rdb
```

### Scheduled Jobs

Fly has no built-in scheduler — you typically ran a cron Machine or a supervised process. In Hop3, declare a worker in `hop3.toml`:

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

### Multi-Region

This is the gap that matters most for Fly users, so it's worth being plain about it. Hop3 runs on one server. There is no `primary_region`, no `fly regions add`, no anycast, no edge. If your app served users on multiple continents from multiple regions, Hop3 does not replace that — pick the region closest to your users, put the server there, and accept the latency for everyone else. The flip side is data locality: everything lives in one place you chose, which for a lot of apps (and a lot of compliance regimes) is the feature, not the limitation.

## Command Mapping

| Fly.io Command | Hop3 Command |
|----------------|--------------|
| `fly apps create` | `hop3 app create` |
| `fly apps list` | `hop3 app list` |
| `fly status` | `hop3 app status --app X` |
| `fly secrets list` | `hop3 env show --app X` |
| `fly secrets set` | `hop3 env set K=V --app X` |
| `fly logs` | `hop3 app logs --app X` |
| `fly machine list` | `hop3 ps --app X` |
| `fly scale count` | `hop3 ps scale --app X web=N` |
| `fly apps restart` | `hop3 app restart --app X` |
| `fly ssh console` / `fly console` | `hop3 app run --app X` |
| `fly postgres create` | `hop3 addon create postgres <name>` |
| `fly postgres attach` | `hop3 addon attach <name> --app X` |
| `fly volumes create` | `[[volumes]]` in `hop3.toml` |
| `fly certs add` | `hop3 domain add <host> --app X` |

## Cost and Lock-In

Fly's pricing is per-Machine, per-region, per-volume, with bandwidth on top, and it's usage-based — which is great until a region you forgot about, or a Machine that wouldn't scale to zero, shows up on the invoice. The bill moves. Hop3's doesn't: you rent a VPS, you know the number, and adding an app or a region's worth of traffic doesn't change it.

| | Fly.io | Hop3 (self-hosted) |
|-|--------|-------------------|
| Compute | per-Machine, per-region | fixed VPS |
| Postgres | per-Machine + volume | included on the VPS |
| Bandwidth | metered | included (VPS allowance) |
| **Small app** | usage-based, climbs with regions | ~$10/month (VPS) |
| **Medium app** | usage-based | ~$30/month (VPS) |

The lock-in angle is the quieter win. On Fly your app is shaped around Fly Machines, 6PN private networking, and `fly.dev` hostnames. On Hop3 it's a Dockerfile (or a plain native build), a Postgres you can `pg_dump`, and a config file in your repo — nothing that only one vendor can run. If you ever leave Hop3 too, you leave with a standard app, not a platform-shaped one. The trade-off is the obvious one: you manage the server, but you control everything on it.

## Rollback Plan

Keep your Fly app running during migration — Machines you don't touch keep serving:

1. Deploy to Hop3 with a test domain (or a `*.fly.dev`-style subdomain of your own)
2. Verify everything works against real data
3. Switch DNS to point at your Hop3 server
4. Keep the Fly app running for 1–2 weeks
5. Run `fly apps destroy your-app` (and `fly postgres` / `fly volumes`) once you're confident

Because DNS is the only switch, rollback is just pointing the record back at Fly — no data has to move twice.

## Getting Help

- [Hop3 Documentation](https://hop3.cloud)
- [GitHub Issues](https://github.com/abilian/hop3/issues)
- [Troubleshooting Guide](/guides/troubleshooting/)

---

*Coming from a different platform? The concepts are similar. Check the [Getting Started guide](/get-started/) for a fresh start.*
