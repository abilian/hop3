# Migrating from AWS Elastic Beanstalk to Hop3

Elastic Beanstalk promised to hide the AWS machinery, but the machinery never really went away. You still write `.ebextensions/*.config`, you still reason about the load balancer and the autoscaling group, you still wait on AMI rebuilds, and you still get the AWS bill at the end of the month — for a CloudFormation stack you mostly didn't choose. If what you actually wanted was one predictable server that runs your app, Hop3 gives you that without the ceremony. This guide helps you migrate an existing Elastic Beanstalk environment to Hop3.

## What's Similar

If you came to Elastic Beanstalk for its managed-platform feel, a lot carries over:

| Elastic Beanstalk | Hop3 |
|-------------------|------|
| EB platform (Python, Node, Ruby, …) | Native toolchain (auto-detected) |
| `Procfile` | `Procfile` (compatible) |
| `eb deploy` | `git push hop3 main` |
| Environment properties | `hop3 env set` / `[env]` |
| `eb setenv FOO=bar` | `hop3 env set FOO=bar --app myapp` |

Your `Procfile` works unchanged — Elastic Beanstalk reads a `Procfile`, and so does Hop3. The process model you already declared there comes across as-is.

One syntactic difference to keep in mind: the EB CLI infers the environment from the local `.elasticbeanstalk/` directory, while Hop3 targets the app with the `--app` flag (never a positional argument, never colon syntax). So `eb setenv FOO=bar` becomes `hop3 env set FOO=bar --app myapp`.

## What's Different

This is where Elastic Beanstalk's AWS-shaped assumptions stop applying. Read this section before you start — two of these gaps matter a lot for an EB user.

| Elastic Beanstalk | Hop3 |
|-------------------|------|
| Managed platform on AWS | Self-hosted, one server |
| ELB + autoscaling group | Single server, manual `ps scale` |
| Worker environment tier (SQS) | `[run.workers]` (no managed queue) |
| RDS managed database | PostgreSQL / MySQL addon, or keep RDS |
| Many AWS-integrated services | PostgreSQL, MySQL, Redis, S3/MinIO — and growing |
| Multiple environments / cloning | Deploy named apps manually |

Two of these deserve to be stated plainly:

- **No load balancer or autoscaling group.** Elastic Beanstalk fronts your app with an ELB and scales an ASG up and down on a metric. Hop3 runs your app on one server, and you set the process count yourself with `hop3 ps scale`. There is no automatic scale-out and no multi-instance load balancing across machines — Hop3 is a single-server PaaS, with no multi-region, cluster, or edge tier. If your workload genuinely needs an ASG, that's a reason to stay on EB.
- **No managed queue for the worker tier.** EB's *worker environment tier* is wired to an SQS queue that delivers messages to your app over HTTP. Hop3 has no managed-queue equivalent. You can still run background workers (see [The worker tier](#the-worker-tier) below), but you bring your own broker (Redis, for instance) or use cron — there is no SQS to point at.

Hop3 is simpler. You manage one server instead of a CloudFormation stack, an ELB, an ASG, and a fleet of EC2 instances.

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

## Step 2: Export Your Elastic Beanstalk Configuration

Your environment properties are the equivalent of config vars. Pull them out of the environment so you can re-set them on Hop3:

```bash
eb printenv -e your-env
```

Review the output and drop the variables Hop3 manages for you:

- `DATABASE_URL` / RDS connection vars — set by a Hop3 addon if you move the database (or kept as-is if you keep RDS, see Step 4)
- `PORT` — auto-set by Hop3
- Any `AWS_*` / EB-internal variables tied to the old environment

Everything that's left is genuine application config that belongs in `[env]`.

## Step 3: Translate `.ebextensions` into `hop3.toml`

This is the heart of the migration. Elastic Beanstalk keeps its per-environment build and deploy logic in `.ebextensions/*.config` files (and in `container_commands` / `commands` blocks). There is no automatic importer for these — the one configuration importer Hop3 ships is `hop3 app migrate procfile <dir>`, which turns a `Procfile` into a starter `hop3.toml`. Everything else from `.ebextensions` is translated by hand. The mapping is mechanical:

| Elastic Beanstalk | Hop3 (`hop3.toml`) |
|-------------------|--------------------|
| EB platform / solution stack | `[build] toolchain` (usually auto-detected) |
| `commands:` (run early, before app) | `[build] before-build` |
| `container_commands:` (run after build, before deploy) | `[run] before-run` |
| Environment properties (`option_settings`) | `[env]` |
| `Procfile` web/worker processes | `Procfile` (kept as-is) or `[run]` / `[run.workers]` |
| ELB health check path | `[healthcheck] path` |

A representative `.ebextensions/01-app.config` like this:

```yaml
option_settings:
  aws:elasticbeanstalk:application:environment:
    DJANGO_SETTINGS_MODULE: myapp.settings.production
    SECRET_KEY: your-secret-key
  aws:elasticbeanstalk:environment:proxy:
    HealthCheckPath: /health/

commands:
  01_install_assets:
    command: "npm install && npm run build"

container_commands:
  01_migrate:
    command: "python manage.py migrate --noinput"
    leader_only: true
```

becomes this `hop3.toml`:

```toml
[metadata]
id = "your-app"

[build]
toolchain = "python"
before-build = "npm install && npm run build"

[run]
before-run = ["python manage.py migrate --noinput"]

[env]
DJANGO_SETTINGS_MODULE = "myapp.settings.production"
SECRET_KEY = "your-secret-key"

[healthcheck]
path = "/health/"
```

A few notes on the translation:

- `commands:` run *before* your application is built, so they map to `[build] before-build`. `container_commands:` run *after* the build, just before the new version goes live — that's `[run] before-run`.
- EB's `leader_only: true` (run a `container_command` on exactly one instance) has no direct knob because Hop3 runs one server: a `before-run` command runs once per deploy, which is the behavior you wanted from `leader_only` anyway.
- `option_settings` that configure environment *properties* become `[env]`. The many other `option_settings` namespaces — the ones that size the ELB, set ASG min/max, pick instance types, or tune the proxy — describe AWS infrastructure Hop3 doesn't have, so they simply have no equivalent. That's not a gap to work around; it's infrastructure you no longer run.

### The worker tier

If you ran a separate EB *worker environment*, its process belongs in `[run.workers]` on the same Hop3 app:

```toml
[run.workers]
worker = "celery -A myapp worker"
```

The important caveat, repeated from above: EB's worker tier is fed by an SQS queue, and Hop3 has no managed queue. Your worker still runs, but it needs a broker you provide — typically a Redis addon (`hop3 addon create redis your-app-cache`) that your worker reads from — or, for periodic jobs, system cron:

```bash
ssh root@your-server.com
crontab -e
# Add: 0 * * * * /home/hop3/apps/your-app/venv/bin/python /home/hop3/apps/your-app/src/manage.py cleanup
```

## Step 4: Migrate Your Database

Elastic Beanstalk apps usually talk to RDS. You have two clean options.

### Option A — keep RDS

If RDS is working for you and you only want to move the compute, leave the database where it is. Point Hop3 at the existing RDS endpoint through `[env]` (or `hop3 env set`):

```bash
hop3 env set --app your-app \
  DATABASE_URL=postgresql://user:pass@your-db.abc123.us-east-1.rds.amazonaws.com:5432/yourdb
```

Make sure the RDS security group allows connections from your new Hop3 server's IP. Nothing else changes — Hop3 doesn't require its own addon, an external managed database is fine.

### Option B — move the database onto Hop3

To consolidate onto the one server, create a PostgreSQL addon and migrate the data.

First, create the addon and attach it to your app:

```bash
hop3 addon create postgres your-app-db
hop3 addon attach your-app-db --app your-app
```

Get the connection details:

```bash
hop3 addon show your-app-db
```

Dump RDS and restore into the addon:

```bash
# Dump from RDS (run from a host that can reach RDS)
pg_dump -Fc -h your-db.abc123.us-east-1.rds.amazonaws.com -U user yourdb > rds.dump

# Copy the dump to the Hop3 server and restore
scp rds.dump root@your-server.com:/tmp/
ssh root@your-server.com
sudo -u postgres pg_restore --verbose --no-owner \
    -d your_app_db /tmp/rds.dump
```

If your RDS instance is MySQL, create a `mysql` addon instead and use `mysqldump` / the matching restore. Hop3's addons are PostgreSQL, MySQL, Redis, and S3/MinIO — and growing. There's no managed MongoDB or message queue; for those, keep the AWS-side service and point `[env]` at it, exactly like Option A.

### RDS Postgres extensions

If your app relies on Postgres extensions (like `pg_stat_statements`), enable them through the addon command — no SSH or manual `psql` needed:

```bash
hop3 addon postgres extensions your-app-db pg_stat_statements
```

Extensions are allow-listed, so only the ones Hop3 ships support for will install.

## Step 5: Deploy to Hop3

Add Hop3 as a Git remote:

```bash
git remote add hop3 hop3@your-server.com:your-app
```

Deploy:

```bash
git push hop3 main
```

Where you used to run `eb deploy`, you now `git push hop3 main`. The build runs on the server: Hop3 detects the toolchain (Python, Node.js, Go, Ruby, Rust, Java, PHP, Elixir, .NET), runs your `before-build`, installs dependencies, runs `before-run`, and starts the processes from your `Procfile` / `[run]` config.

If your EB platform pinned a specific runtime version that the server's native toolchain doesn't match, switch that app to the Docker builder and pin it in your image:

```toml
[build]
builder = "docker"
```

## Step 6: Scale and Point Your Domain

### Scaling

There's no autoscaling group to configure — and no ELB scaling policy to translate. Set the process count yourself:

```bash
hop3 ps scale --app your-app web=3
```

You can scale workers the same way (`worker=2`). This is manual on purpose: Hop3 is a single server, so scaling means adjusting how many worker processes that server runs, not adding instances behind a load balancer.

### Domain and TLS

Update your DNS to point at the Hop3 server:

```
your-app.example.com  A  your-server-ip
```

You can bind the hostname declaratively in `hop3.toml`:

```toml
[domains]
list = ["your-app.example.com"]
```

or from the CLI:

```bash
hop3 domain add your-app.example.com --app your-app
```

Out of the box, a freshly installed server serves a self-signed certificate. Once Let's Encrypt/ACME is configured on the server, Hop3 requests a real certificate for the domain at deploy time — no ACM certificate or ELB listener to wire up.

## Command Mapping

| Elastic Beanstalk | Hop3 |
|-------------------|------|
| `eb create` | `hop3 app create` |
| `eb list` | `hop3 app list` |
| `eb status` | `hop3 app status --app X` |
| `eb printenv` | `hop3 env show --app X` |
| `eb setenv K=V` | `hop3 env set K=V --app X` |
| `eb deploy` | `git push hop3 main` (or `hop3 deploy`) |
| `eb logs` | `hop3 app logs --app X` |
| `eb ssh` then run a command | `hop3 app run --app X` |
| `eb scale N` | `hop3 ps scale --app X web=N` |
| `eb restart-app-server` | `hop3 app restart --app X` |
| (RDS via console) | `hop3 addon create` / `hop3 addon attach` / `hop3 addon show` |
| (EB env in maintenance) | `hop3 app stop --app X` |

## The Cost and Lock-In Angle

Elastic Beanstalk itself is "free" — but the environment underneath it is a full AWS bill: EC2 instances sized for headroom, an ELB you pay for by the hour and by the gigabyte, RDS, the NAT gateway, the data transfer, and the EBS volumes for the AMIs. A modest EB environment with a load-balanced tier and a small RDS instance comfortably runs into the low-to-mid hundreds of dollars a month before you've served much traffic. A single VPS that runs the same app on Hop3 is typically $10–$30/month.

The deeper cost is the lock-in: `.ebextensions`, the solution-stack platform, the ASG and ELB config, and the AMI rebuild cycle are all AWS-shaped. The Hop3 side is plain — a `hop3.toml`, a `Procfile`, and a Git remote — and the server is yours, on any provider. The trade-off is real and worth stating: you give up the autoscaling group, the managed load balancer, and the SQS-backed worker tier, and you take on managing one server. If those AWS features are load-bearing for you, Hop3 isn't the right move. If they were ceremony you were paying for and rarely using, this is a simpler, cheaper place to land.

## Rollback Plan

Keep your Elastic Beanstalk environment running during the migration. Cutover is just DNS:

1. Deploy to Hop3 with a test hostname and verify the app end to end (run a real request, not just a health check).
2. If you chose Option A, confirm the new server reaches RDS; if Option B, confirm the data restored correctly.
3. Switch DNS from the EB environment's CNAME to the Hop3 server's A record.
4. Keep the EB environment up for 1–2 weeks as a fallback — flipping DNS back is instant.
5. When you're confident, `eb terminate` the environment (and tear down the RDS instance if you moved the database).

## Getting Help

- [Hop3 Documentation](https://hop3.cloud)
- [GitHub Issues](https://github.com/abilian/hop3/issues)
- [Troubleshooting Guide](/guides/troubleshooting/)

---

*Coming from a different platform? The concepts are similar. Check the [Getting Started guide](/get-started/) for a fresh start.*
