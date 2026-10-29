# Migrating from a hand-rolled VPS to Hop3

You already run the box. You wrote the nginx vhost and the systemd unit and put certbot on a cron. Your deploy is muscle memory: `ssh in`, `git pull`, `pip install -r requirements.txt`, `systemctl restart myapp`. It works. It has worked for years.

Yet you maintain every one of those pieces. None of them is the app. The nginx config drifts. The certbot renewal fails one Sunday without a word; you find out when the browser does. A dependency bump breaks the deploy and now you're debugging on the live server at the worst possible time. You are running a tiny PaaS that you built yourself and have to keep building. Hop3 is that PaaS, already built. It runs on the same kind of box you already understand, with no Docker or Kubernetes required. It keeps the server yours and maintains nginx, systemd units, and certbot for you. Your deploy becomes `git push`.

This is the easiest migration of all, because you already think in processes, a reverse proxy, and a TLS cert. Hop3 does those three chores the same way you would, automatically. This guide moves one app over to Hop3, primitive by primitive.

## What's Similar

You're naming the things you already do:

| Your VPS | Hop3 |
|-------------------|------|
| `ssh in; git pull; systemctl restart` | `git push hop3 main` |
| Your start command (gunicorn/uWSGI) | `Procfile` / `[run]` |
| `systemd Environment=` / a `.env` | `[env]` in `hop3.toml` |
| `apt install postgresql` | `hop3 addon create postgres` |
| Editing the nginx `server_name` | `hop3 domain add` |

The runtime is the same one you already run: nginx out front, a process supervised below it, a Postgres on the box. Hop3 owns the wiring. The CLI always takes the target app as an `--app` flag. So where you'd `sudo -u myapp env | grep` to read config, you `hop3 env show --app myapp`.

## What's Different

| Your VPS | Hop3 |
|-------------------|------|
| You write the nginx vhost | Hop3 generates and reloads it |
| You write the systemd unit | Hop3 supervises the process (uWSGI) |
| certbot on a cron you maintain | ACME requested at deploy time |
| `git pull` + a restart ritual | `git push hop3 main` |
| A Postgres you installed and babysit | A managed addon (or keep yours) |
| You decide the layout | Hop3 expects its layout (`$PORT`, app/venv tree) |

The trade-off is ownership: Hop3 takes over nginx and process management. In exchange, your app binds the `$PORT` Hop3 assigns and lives in the app/venv tree Hop3 lays out. For a single web app that's a straight swap. A box crowded with unrelated services (a mail stack, a bespoke nginx doing clever `location` routing for three different things) is harder to move, because Hop3 wants to own the reverse proxy. Move the app; leave the rest where it is until you're ready.

You can do this on the very same VPS, because Hop3 installs onto a Linux box you already have.

## Step 1: Set Up Your Hop3 Server

Provision a server, or use the one you already have. Ubuntu 24.04 LTS is recommended; Debian, Fedora, and Rocky/Alma also work. Install Hop3:

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

If you're installing onto the box your app already lives on, note that Hop3 wants to own nginx and the firewall ports for the apps it manages. Plan to retire your vhost for the app you're migrating once Hop3 is serving it (Step 6), so nothing else fights Hop3 for port 443.

## Step 2: Inventory What You Wired by Hand

There's no config to export, because your configuration is spread across the system. Walk these four spots and write down what you find; each maps onto a single Hop3 concept in Step 3.

```bash
# Your start command — read it off the unit
systemctl cat myapp.service

# Your environment — from the unit's Environment= lines, or a .env / EnvironmentFile
grep -h Environment /etc/systemd/system/myapp.service
cat /etc/myapp/env        # or wherever your EnvironmentFile points

# Your nginx vhost — the proxy_pass target and server_name
cat /etc/nginx/sites-enabled/myapp

# Your certbot setup — which domains, and the renewal cron/timer
certbot certificates
```

Note three things from the unit and vhost: the **command** that starts your app (`ExecStart=`), the **port** it binds (you'll stop hardcoding it), and the **`server_name`** nginx routes to it. Then plan to drop the entries Hop3 sets for you:

- `DATABASE_URL`: set by the Hop3 Postgres addon (or kept, if you point at your existing DB; see Step 4)
- `REDIS_URL`: set by the Hop3 Redis addon
- `PORT`: auto-set by Hop3; your app reads `$PORT`
- Anything nginx- or systemd-specific that only made sense in your old setup

## Step 3: Add hop3.toml

The four chores collapse into one file. A representative Django app is three artifacts. The systemd unit:

```ini
# /etc/systemd/system/myapp.service
[Service]
WorkingDirectory=/srv/myapp
EnvironmentFile=/etc/myapp/env
ExecStart=/srv/myapp/venv/bin/gunicorn myapp.wsgi --bind 127.0.0.1:8000 --workers 3
ExecStartPre=/srv/myapp/venv/bin/python manage.py migrate
Restart=always
```

The nginx vhost:

```nginx
# /etc/nginx/sites-enabled/myapp
server {
    server_name myapp.example.com;
    location / { proxy_pass http://127.0.0.1:8000; }
    # ... plus the certbot-managed listen 443 / ssl_certificate lines
}
```

`/etc/myapp/env` is your `Environment=` by another name.

The same app as `hop3.toml`:

```toml
[metadata]
id = "myapp"

[env]
# From /etc/myapp/env — minus DATABASE_URL/PORT, which Hop3 sets
SECRET_KEY = "your-secret-key"
DJANGO_SETTINGS_MODULE = "myapp.settings.production"

[build]
toolchain = "python"

[run]
before-run = ["python manage.py migrate"]

[healthcheck]
path = "/health/"
```

Each line of that file replaces a piece of your old setup:

- **The systemd unit disappears.** Your `ExecStart` gunicorn command becomes the app's process model. Hop3 supervises it (via uWSGI) and restarts it for you. That's the `Restart=always` you used to write. Put the web process in a `Procfile` (`web: gunicorn myapp.wsgi`) or let Hop3's Python toolchain detect it; either way you stop maintaining a unit file. `hop3 app migrate procfile . --dry-run` will scaffold a starting `hop3.toml` from an existing `Procfile`.
- **`ExecStartPre=… migrate` → `[run] before-run`.** The pre-start step you bolted onto the unit becomes an explicit, ordered command that runs on every deploy.
- **`EnvironmentFile` → `[env]`.** The non-secret values from `/etc/myapp/env` move into `[env]`. Set the secrets with `hop3 env set`, which stores them encrypted on the server and keeps them out of the repo; Hop3 refuses a credential committed under `[env]`. Drop `DATABASE_URL` and `PORT`.
- **`--bind 127.0.0.1:8000` → bind `$PORT`.** Hop3 assigns a dynamic `$PORT`, sets it in the environment, and routes the proxy to it by hostname. Change `--bind 127.0.0.1:8000` to `--bind 0.0.0.0:$PORT` (or have your framework read `PORT`). This is the one code-shaped change the migration asks of you.
- **The nginx vhost disappears.** Hop3 generates the `server`/`proxy_pass` config from `[metadata].id` and the domain you bind, and reloads nginx itself. You stop editing `sites-enabled`.
- **The `[healthcheck]` is new.** systemd only knew whether the process was alive; Hop3 can probe an HTTP path and refuse to flip traffic to a deploy that doesn't answer.

## Step 4: Migrate Your Database

You installed Postgres on the box yourself (`apt install postgresql`, `createdb`, a `pg_hba.conf` line). You have two options.

### Option A: Hand it to a Hop3 addon

Dump your existing database the ordinary way:

```bash
sudo -u postgres pg_dump -Fc myapp_production > latest.dump
```

Create the addon and attach it. This replaces your `createdb` and the `DATABASE_URL` you wrote into `/etc/myapp/env`:

```bash
hop3 addon create postgres myapp-db
hop3 addon attach myapp-db --app myapp
```

Get the connection details:

```bash
hop3 addon show myapp-db
```

Import the dump:

```bash
# Turn the dump into SQL and load it into the addon (where the hop3 CLI runs)
pg_restore --no-owner --no-acl -f latest.sql latest.dump
hop3 addon postgres import myapp-db --confirm=myapp-db < latest.sql
```

From here Hop3 injects `DATABASE_URL` on every deploy, so you never write it again.

### Option B: Keep the Postgres you already run

Maybe your database is finely tuned and you're not ready to move it. You don't have to. Skip the addon and set the local instance's URL on the server, exactly as your old `.env` did (`hop3.toml` refuses a connection string with credentials in it):

```bash
hop3 env set --app myapp DATABASE_URL="postgresql://myapp:pass@127.0.0.1:5432/myapp_production"
```

Backups, extensions, and upgrades of that database stay your job. The app talks to it byte-for-byte as before. You can adopt a Hop3 addon later when you're ready to let it take over.

### Postgres Extensions

If your database relied on an extension (`pg_stat_statements`, `pgcrypto`, …) and you move to an addon, enable it through the addon command (no `psql` as `postgres` needed):

```bash
hop3 addon postgres extensions myapp-db pg_stat_statements
```

Extensions are allow-listed, so only the ones Hop3 supports will install.

### Redis

If you ran a local Redis, the same fork applies: `hop3 addon create redis myapp-cache` and attach it (Hop3 injects `REDIS_URL`), or point `[env]` at your existing instance. Most Redis is cache and doesn't need migrating, so let it warm up fresh.

## Step 5: Deploy to Hop3

This is the line that retires the whole `ssh in; git pull; pip install; systemctl restart` ritual. Add Hop3 as a git remote:

```bash
git remote add hop3 hop3@your-server.com:myapp
```

Deploy by pushing:

```bash
git push hop3 main
```

On push, Hop3 does everything your ritual did, in order and on its own: checks out the code, builds it with the Python toolchain (creates the venv, installs `requirements.txt`), runs your `before-run` migration, supervises the process, writes the nginx config, and reloads the proxy. Your next deploy is the same one line, with no SSH session or manual restart.

## Step 6: Point Your Domain (and Retire the Old vhost)

Your old setup had nginx listening on 443 with a certbot-issued cert. Hop3 takes that over. Point DNS at the server (unchanged if you're on the same box):

```
myapp.example.com  A  your-server-ip
```

Bind the hostname so Hop3 generates the vhost for it:

```bash
hop3 domain add myapp.example.com --app myapp
```

Once Let's Encrypt is configured on the server, Hop3 requests a certificate for the domain at deploy time. The certbot cron goes with it. Out of the box, a freshly installed server serves a self-signed certificate until you point it at an ACME provider. If you're migrating on the same machine, disable your old vhost (`rm /etc/nginx/sites-enabled/myapp && nginx -s reload` before Hop3 takes 443) so the two configs don't collide.

## Common Migration Issues

### "But I liked owning the nginx config"

The objection is common, and fair. You wrote that vhost for a reason: a rate-limit rule, a `client_max_body_size`, a `location` block for static files. Hop3 owns the generated config, so an edit to its file is overwritten on the next deploy. Most of what you customized has a first-class home: static files come from your framework or the static-site builder, body size and timeouts are proxy concerns Hop3 sets sanely, and domains are `hop3 domain add`. If you need nginx behavior Hop3 doesn't expose, raise it as a gap; don't paper over it with an edit the next `git push` will erase.

### Pinned Python (or Node) Version

Your VPS used whatever `python3` you `apt install`ed, or a `pyenv` you set up. Hop3's native toolchain uses the system Python (3.11–3.13 depending on OS). If your app needs a specific runtime your server's Python can't provide, switch that app to the Docker builder and pin it in your image:

```toml
[build]
builder = "docker"
```

There's also a Nix builder for reproducible, pinned toolchains without a Dockerfile.

### Persistent Files Written Outside the Repo

A VPS app often writes uploads or generated files into a directory next to the code (`/srv/myapp/uploads`). On Hop3 the source tree is replaced on every deploy, so anything written inside it is lost. Declare a volume; Hop3 keeps it across redeploys:

```toml
[[volumes]]
name = "uploads"
target = "data/uploads"
```

`target` is a directory inside the app's data root (relative, no `..`), not an absolute server path. Point your app's upload setting at it.

### A Non-HTTP Port the App Binds Directly

If your app also bound a raw, fixed host port (something other than the HTTP one), that's outside the proxied `$PORT` path. Your web traffic uses the dynamic `$PORT` and is proxied by hostname, so it never declares a port. A fixed host port is declared explicitly:

```toml
[[ports]]
number = 1935
protocol = "tcp"
name = "rtmp"
```

Hop3 records each fixed port in a host-wide registry and refuses a second app that wants the same one, before it builds, so two apps cannot collide on it. Hop3 opens the firewall for fixed ports only on native and Nix builds. A Docker-deployed app claims the port (so the conflict check works), but its firewall port stays closed for now. Use a native or Nix build for an app that needs a reachable fixed port.

### Scheduled Jobs (Your Other Crontab Entries)

Beyond certbot, you probably had app cron jobs: a nightly cleanup, a digest mailer. On Hop3 they have two homes. A long-running scheduler is a worker in `hop3.toml`:

```toml
[run.workers]
scheduler = "celery -A myapp beat"
```

Or keep using system cron on the one box; it's still your server:

```bash
# On a machine where the hop3 CLI is signed in to the server
crontab -e
# Add: 0 * * * * hop3 app run --app myapp python manage.py cleanup
```

### Scaling

You scaled by editing `--workers 3` in the unit and running `systemctl restart`. Hop3 scales the same idea explicitly, but there's no autoscaling; it stays manual:

```bash
hop3 ps scale --app myapp web=3 worker=2
```

## Command Mapping

| What you did | Hop3 Command |
|----------------------|--------------|
| `ssh in; git pull; systemctl restart` | `git push hop3 main` (or `hop3 deploy`) |
| Read the unit / `systemctl status` | `hop3 app status --app X` |
| `journalctl -u myapp -f` | `hop3 app logs --app X` |
| `systemctl restart myapp` | `hop3 app restart --app X` |
| `systemctl stop myapp` | `hop3 app stop --app X` |
| `grep Environment /etc/.../myapp.service` | `hop3 env show --app X` |
| Edit `EnvironmentFile`; restart | `hop3 env set K=V --app X` |
| `sudo -u myapp python manage.py shell` | `hop3 app run --app X` |
| Edit `server_name`; `nginx -s reload` | `hop3 domain add <host> --app X` |
| `apt install postgresql; createdb` | `hop3 addon create postgres <name>` |
| Edit `--workers N`; restart | `hop3 ps scale --app X web=N` |

## Cost and Lock-In

The cost story barely moves: you were already paying for a VPS; you still pay for one VPS. There is no managed-platform premium or per-feature line item. Hop3 itself is open source. You are buying your afternoons back: the ones you spent debugging a failed certbot renewal, a drifted nginx config, or a deploy that broke on the live box.

| | Hand-rolled VPS | Hop3 (self-hosted) |
|-|-----------------|--------------------|
| Compute | one VPS | the same one VPS |
| nginx / systemd / certbot | you maintain them | Hop3 generates and manages them |
| Deploy | manual SSH ritual | `git push` |
| **Small app** | ~$10/month (VPS) | ~$10/month (VPS) |
| **Medium app** | ~$30/month (VPS) | ~$30/month (VPS) |

On lock-in, you are already in the best possible spot. Hop3 keeps you there. A VPS app has no vendor under it. After migrating, it still doesn't: it's a standard app, a `git push` away from deploying, with a Postgres you can `pg_dump` and a `hop3.toml` in the repo. Nothing here is shaped around a vendor's API. If you ever leave Hop3, you leave the same way you arrived, with an ordinary app and a server you control. The trade-off is the one you already accept: you manage the box. Hop3 manages the parts of it that aren't your app.

## Rollback Plan

Your old setup is still right there on disk, which makes rollback the safest migration of the lot:

1. Deploy to Hop3 under a test domain (or a subdomain like `new.myapp.example.com`), with your old vhost still serving the real one
2. Verify everything works against real data
3. Disable the old nginx vhost and let Hop3 take the production hostname (Step 6)
4. Leave the old systemd unit and vhost on disk: run `systemctl disable --now myapp` and move the nginx file aside; don't delete them
5. Once you're confident (give it a week or two), remove the old unit, vhost, and any unused packages

Because the old process and config are only *disabled*, rolling back is one `systemctl enable --now myapp` and restoring the nginx file, so no data has to move twice.

## Getting Help

- [Hop3 Documentation](https://hop3.cloud)
- [GitHub Issues](https://github.com/abilian/hop3/issues)
- [Troubleshooting Guide](/guides/troubleshooting/)

---

*Coming from a different platform? The concepts are similar. Check the [Getting Started guide](/get-started/) for a fresh start.*
