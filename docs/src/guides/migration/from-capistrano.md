# Migrating from Capistrano to Hop3

Capistrano deploys your code beautifully — `cap production deploy`, a clean `releases/` directory, an atomic symlink swap, and `cap deploy:rollback` when something goes wrong. But Capistrano stops at your code. The server underneath it — Nginx, Puma or Unicorn, systemd units, TLS certificates, the database, the directory that holds your uploads — you built and maintain all of that by hand. Capistrano automates the deploy; it never automated the box. This guide helps you move a Capistrano-deployed app to Hop3, where git-push deploys *and* the server plumbing are both managed for you.

## What's Similar

If you've used Capistrano, the Hop3 workflow will feel familiar:

| Capistrano | Hop3 |
|------------|------|
| `cap production deploy` | `git push hop3 main` |
| `deploy.rb` tasks (`bundle install`, `db:migrate`) | `[build] before-build` / `[run] before-run` |
| `before`/`after` hooks | `before-build` / `before-run` commands |
| `cap deploy:rollback` | redeploy a previous commit |
| `shared/` directories (uploads, etc.) | `[[volumes]]` |

Both are SSH-based and Git-driven. You still `git push` to ship, and your build/migrate steps still run on the server.

One difference to keep in mind from the start: Capistrano targets a *stage* (`cap production deploy`), and the app it operates on is implicit in your `deploy.rb`. In Hop3 the app you're targeting is always the `--app` flag, never a positional argument or a colon — so a Capistrano `cap production deploy` becomes `git push hop3 main` (or `hop3 deploy --app myapp`), and a one-off task like `cap production rails:console` becomes `hop3 app run --app myapp bin/rails console`.

## What's Different

| Capistrano | Hop3 |
|------------|------|
| You build the server (Nginx, Puma, systemd, certs) | Hop3 manages all of it |
| Targets many servers / roles | Single server |
| Rollback = instant symlink swap | Rollback = redeploy of an earlier commit |
| You provision the database yourself | `hop3 addon create` |
| No process supervision of its own | uWSGI-managed processes, `hop3 ps scale` |

This is the heart of the move. Capistrano is a deploy *tool* that assumes you've already stood up — and will keep maintaining — the runtime. Hop3 is a small PaaS: it configures the reverse proxy, supervises the processes, provisions the database, and requests the certificate, so the parts of your Capistrano setup that were really "server administration in Ruby" simply go away.

Be clear-eyed about the trade-offs, though. Capistrano can fan a deploy out across a fleet with roles (`:app`, `:web`, `:db`); Hop3 deploys to one server. And Capistrano's rollback is an atomic symlink flip between two already-built releases — near-instant. Hop3's rollback is a redeploy of an earlier commit, which rebuilds. If those two properties are load-bearing for you, weigh them before you switch.

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

This is the step that used to be a Capistrano provisioning recipe — or an Ansible playbook next to it — installing Nginx, Ruby, a process manager, and certbot. With Hop3 those come with the server.

## Step 2: Read Off Your Capistrano Config

There's no automatic importer for `deploy.rb` — that translation is done by hand, and it's a useful exercise because most of `deploy.rb` describes server layout that Hop3 now owns. Open your `config/deploy.rb` and the stage files (`config/deploy/production.rb`) and pull out the parts that are *about your app* rather than *about the server*:

- **Build and release tasks** — `bundle install`, `rails db:migrate`, `rails assets:precompile`, and any `before`/`after` hooks. These become `before-build` / `before-run` in `hop3.toml`.
- **`linked_files` / `linked_dirs`** — your `shared/` entries (`storage`, `public/uploads`, `public/system`). These become `[[volumes]]`.
- **Environment** — anything you set with `set :rails_env` or pushed onto the server out of band (`SECRET_KEY_BASE`, `RAILS_MASTER_KEY`, third-party API keys). These become `[env]` or `hop3 env set`.
- **The process command** — your `puma.rb` invocation, your Sidekiq worker. These become the `web` / worker entries.

What you can *drop*: `set :deploy_to`, `:keep_releases`, the `releases/` and `current` symlink machinery, the Nginx/Puma/systemd templates in your `config/` or Chef/Ansible repo, and the certbot cron. Hop3 owns all of that.

## Step 3: Add hop3.toml

A `Procfile` works if you already have one (and `hop3 app migrate procfile <dir>` will generate a starting `hop3.toml` from it — that's the only config importer; everything else here is translated by hand). For a Rails app, `hop3.toml` maps cleanly onto what `deploy.rb` used to express:

```toml
[metadata]
id = "your-app"

[build]
before-build = ["bin/rails assets:precompile"]

[run]
before-run = "bin/rails db:migrate"

[env]
RAILS_ENV = "production"
RAILS_LOG_TO_STDOUT = "true"
RAILS_SERVE_STATIC_FILES = "true"
SECRET_KEY_BASE = { generate = "hex", length = 64 }

[healthcheck]
path = "/up"
```

Read that against your `deploy.rb`:

| Capistrano | Hop3 `hop3.toml` |
|------------|------------------|
| `before 'deploy:migrate', 'deploy:assets:precompile'` | `[build] before-build = ["bin/rails assets:precompile"]` |
| `after 'deploy:publishing', 'deploy:migrate'` | `[run] before-run = "bin/rails db:migrate"` |
| `set :rails_env, 'production'` | `[env] RAILS_ENV = "production"` |
| `cap deploy` (Puma start) | the `web` process (see below) |

The Ruby toolchain runs `bundle install` for you, so you don't list it — the same way Capistrano's `bundler` plugin handled it. `SECRET_KEY_BASE = { generate = "hex", length = 64 }` means you no longer push a secret onto the box by hand; Hop3 generates it on first deploy and keeps it stable across redeploys.

### The process model

Where `deploy.rb` told systemd (or your `puma.rb` + a `pumactl` task) how to run the app, Hop3 supervises the processes for you. Declare them with a `Procfile`:

```
web: bundle exec puma -C config/puma.rb
worker: bundle exec sidekiq -C config/sidekiq.yml
```

or as workers in `hop3.toml`:

```toml
[run.workers]
worker = "bundle exec sidekiq -C config/sidekiq.yml"
```

You scale these with `hop3 ps scale` rather than editing a systemd template and re-running Capistrano — see the gap on autoscaling below.

## Step 4: Move Your shared/ Directories to Volumes

Capistrano's `linked_dirs` exist because each release is a fresh checkout, so anything user-uploaded has to live in `shared/` and be symlinked into `current/`. Hop3 has the same problem (each deploy re-extracts your source) and the same shape of solution — a `[[volumes]]` is the managed equivalent of a `shared/` entry:

```toml
[[volumes]]
name = "uploads"
target = "public/uploads"

[[volumes]]
name = "storage"
target = "storage"
```

Each volume survives redeploys, lives outside the replaced source tree, and is captured by `hop3 backup create` by default — so your `shared/public/uploads` and Active Storage `shared/storage` round-trip exactly as they did under Capistrano, without you wiring the symlinks.

## Step 5: Migrate Your Database

Under Capistrano you provisioned PostgreSQL yourself and pointed `database.yml` at it. Hop3 can provision and manage it instead.

### Create and attach the addon

```bash
hop3 addon create postgres your-app-db
hop3 addon attach your-app-db --app your-app
```

Attaching injects `DATABASE_URL` into the app's environment, so your `database.yml` can read `ENV["DATABASE_URL"]` and you stop hand-editing connection strings. Get the connection details with:

```bash
hop3 addon show your-app-db
```

The four addon types Hop3 provisions today are PostgreSQL, MySQL, Redis, and S3/MinIO — and growing. If you run something Hop3 doesn't manage yet, or you want to keep an existing managed database, point `[env]` at its URL instead of creating an addon and skip this step.

### Move the data

Dump from your old server and restore on the new one:

```bash
# On your old server
pg_dump --no-owner --format=custom your_app_production > latest.dump

# Copy to the Hop3 server and restore
scp latest.dump root@your-server.com:/tmp/
ssh root@your-server.com
sudo -u postgres pg_restore --verbose --no-owner \
    -d your_app_db /tmp/latest.dump
```

If your schema uses Postgres extensions (`pg_trgm`, `pgcrypto`, `pg_stat_statements`), enable them through the addon command rather than `psql` as a superuser:

```bash
hop3 addon postgres extensions your-app-db pg_trgm
```

Extensions are allow-listed, so only the ones Hop3 ships support for will install.

### Redis

If your app uses Redis (Sidekiq, Rails cache, Action Cable), create and attach it the same way:

```bash
hop3 addon create redis your-app-cache
hop3 addon attach your-app-cache --app your-app
```

This injects `REDIS_URL`. Most Redis content is cache or a job queue, so starting fresh is usually fine; migrate persisted data only if you rely on it.

## Step 6: Deploy to Hop3

Add Hop3 as a Git remote — the same mental model as a Capistrano stage, except the remote *is* the deploy target:

```bash
git remote add hop3 hop3@your-server.com:your-app
```

Deploy:

```bash
git push hop3 main
```

That single push is your `cap production deploy`. Hop3 detects the Ruby toolchain, runs `bundle install`, runs your `before-build` (asset precompile) and `before-run` (migrate) steps, configures Nginx in front of Puma, and starts the supervised processes. The Nginx vhost and the process supervision that you used to template and maintain are now generated for you.

You can also deploy a working directory without a Git push using `hop3 deploy --app your-app`.

## Step 7: Point Your Domain

Bind the hostname and update DNS:

```bash
hop3 domain add your-app.example.com --app your-app
```

```
your-app.example.com  A  your-server-ip
```

This is the certbot cron you used to babysit. A freshly installed server serves a self-signed certificate out of the box; once you point the server at an ACME provider (Let's Encrypt), Hop3 requests a real certificate for the domain at deploy time. You no longer template Nginx TLS blocks or schedule renewals by hand.

## Common Migration Notes

### Roles and multiple servers

Capistrano roles (`:app`, `:web`, `:db`, `:worker`) let one deploy fan out across a fleet. Hop3 deploys to a single server: web, workers, and the database addon all live on the one box. If your Capistrano setup genuinely spans multiple machines — separate DB host, separate worker tier — that topology doesn't carry over as-is. For many small and mid-size Rails apps the single-server model is exactly right (and is what the `:db` role pointed at a single Postgres host anyway); for a true multi-tier fleet, this is a real limitation to weigh.

### Scheduled jobs (whenever / cron)

Capistrano's `whenever` gem wrote your crontab on deploy. Hop3 doesn't manage cron entries for you yet. Run a scheduler as a worker:

```toml
[run.workers]
scheduler = "bundle exec sidekiq -C config/sidekiq.yml"
```

or add a system cron entry on the server by hand for now.

### Ruby version

Capistrano relied on rbenv/rvm on the server to pin your Ruby. Hop3's Ruby toolchain uses the system Ruby. If you need a specific version the system doesn't provide, use the Docker builder:

```toml
[build]
builder = "docker"
```

### One-off tasks (cap rails:console, rake tasks)

Anything you ran as a Capistrano task — a console, a one-off rake task, a data backfill — runs through `hop3 app run`:

```bash
hop3 app run --app your-app bin/rails console
hop3 app run --app your-app bin/rails db:seed
```

## Command Mapping

| Capistrano | Hop3 |
|------------|------|
| `cap production deploy` | `git push hop3 main` (or `hop3 deploy --app X`) |
| `cap production deploy:rollback` | redeploy an earlier commit (see below) |
| `cap production deploy:restart` | `hop3 app restart --app X` |
| `cap production rails:console` | `hop3 app run --app X bin/rails console` |
| `cap production logs` / `tail` task | `hop3 app logs --app X` |
| `set :rails_env, 'production'` | `hop3 env set RAILS_ENV=production --app X` |
| (server-managed) Puma processes | `hop3 ps --app X` |
| (server-managed) scale | `hop3 ps scale --app X web=N` |
| (server-managed) maintenance | `hop3 app stop --app X` |
| provision Postgres by hand | `hop3 addon create postgres <name>` |
| `cap production doctor` / status | `hop3 app status --app X` |

## Cost and Lock-in

Capistrano is free, and so is Hop3 — neither is the line item. The cost in a Capistrano setup is the *maintenance surface*: the deploy recipes, plus the Nginx configs, the Puma/systemd units, the certbot cron, the database provisioning, and the runbook that keeps them all consistent. That's the part Hop3 removes. You still pay for the VPS (roughly $10–30/month for a small-to-medium Rails app), and you still own the server — but you stop hand-maintaining the layer between "my code" and "a running site."

On lock-in: there's very little to lock into. Your app is unchanged Rails, your database is standard PostgreSQL you can `pg_dump` out at any time, your config is a readable `hop3.toml`, and your deploy is a `git push`. If you ever leave, you leave with a normal Rails app and a normal Postgres dump — the same way you arrived.

## Rollback Plan

Keep your Capistrano-deployed server running through the cutover:

1. Deploy to Hop3 on a temporary hostname and verify the app, the migrations, and the uploaded-file volumes.
2. Run a representative one-off task (`hop3 app run --app your-app bin/rails runner '...'`) to confirm the runtime.
3. Switch DNS to the Hop3 server.
4. Keep the old server live for a week or two.
5. Decommission the old server once you're confident.

For rollbacks *within* Hop3, be aware of the difference from Capistrano up front. There's no instant symlink swap between pre-built releases. To roll back, you redeploy an earlier commit:

```bash
git push hop3 <previous-good-commit>:main
```

This rebuilds, so it's slower than `cap deploy:rollback`. If a release goes bad, the safe sequence is: roll back to the previous commit, and if a migration was involved, restore from the backup you took before deploying (`hop3 backup create` before a risky migration is the equivalent of trusting `keep_releases`). For most apps this is fine; if sub-second rollback is a hard requirement, that's a gap to weigh.

## Getting Help

- [Hop3 Documentation](https://hop3.cloud)
- [Rails on Hop3 tutorial](https://hop3.cloud) and the [Sinatra tutorial](https://hop3.cloud)
- [GitHub Issues](https://github.com/abilian/hop3/issues)

---

*Coming from a different deploy tool? The concepts carry over. Check the [Getting Started guide](/get-started/) for a fresh start.*
