# Migrating to Hop3

Moving an application to Hop3 from another platform. This page is the method that applies whatever you are coming from; the [per-platform guides](#per-platform-guides) below translate one specific platform's primitives, step by step.

If your source platform has a guide, start there and use this page for the parts it does not cover.

## The shape of a migration

Every migration is the same five moves, regardless of source.

**1. Inventory what the app actually needs.** Not what its current platform provides — what the app reads at runtime. The environment variables it consumes, the backing services it opens connections to, the files it writes, the scheduled jobs, the domains that point at it. Anything you cannot name here will be the thing that breaks after cutover.

**2. Translate the configuration.** Your source platform describes the app in *its* format — `app.json`, `fly.toml`, `render.yaml`, `.ebextensions`, a Helm values file, or a chain of imperative `config:set` commands. Hop3 describes it in a `hop3.toml` checked into the repo. This is the step with real work in it, and it is what each per-platform guide spends most of its length on.

**3. Move the data.** Dump from the old backing service, restore into the Hop3 addon. Do this while the old deployment is still serving traffic, verify the restore, and only then cut over. See [Addons](addons.md) for per-service dump and restore commands.

**4. Deploy and verify before touching DNS.** Deploy to Hop3, reach it by its own hostname, and check the app actually works — sign in, exercise a write path, read the logs. A `200` on the homepage is not verification.

**5. Cut over, and keep the rollback.** Point DNS at the new server. Keep the old deployment running and untouched until you are confident; DNS is the fastest thing to change back.

## Set up the server and connect

Common to every guide. Provision a server (Ubuntu 24.04 LTS or later; Debian, Fedora, and Rocky/Alma also work) and install Hop3:

```bash
ssh root@your-server.com
curl -LsSf https://hop3.cloud/install-server.py | sudo python3 -
```

Install the CLI on your local machine:

```bash
hop3-install cli
```

Connect the CLI to your server. On a first install this also creates the admin account and stores your API token:

```bash
hop3 init --ssh root@your-server.com
```

Full detail in [Server Setup](../get-started/server-setup.md).

## From a Procfile

Hop3 reads a Heroku-style `Procfile` as-is, so an app that has one already deploys. You do not need to convert it to migrate — convert it when you want what `hop3.toml` adds: health checks, declared addons, resource limits, backups, and configuration that is reviewable in a diff instead of accumulated on a server.

Convert automatically:

```bash
# Dry run — see what would be generated
hop3 app migrate procfile /path/to/app --dry-run

# Write hop3.toml (your Procfile is backed up to Procfile.bak)
hop3 app migrate procfile /path/to/app
```

Or by hand:

```procfile
prebuild: npm ci && npm run build
prerun: npm run migrate
web: node dist/server.js
worker: node dist/worker.js
```

becomes

```toml
[metadata]
id = "my-app"
version = "1.0.0"

[build]
before-build = ["npm ci", "npm run build"]

[run]
start = "node dist/server.js"
before-run = "npm run migrate"
```

The two can coexist: keep the `Procfile` for the process definitions and add a `hop3.toml` for everything else. Where both describe the same thing, `hop3.toml` wins.

Full key-by-key detail in the [hop3.toml reference](../reference/config.md).

## Environments

Hop3 has one `hop3.toml` per app, not one per environment. Differences between staging and production belong in environment variables, set per deployment:

```bash
hop3 env set --app myapp LOG_LEVEL=info
```

To deploy the same project to more than one server, use contexts (`--context <name>`) rather than branching the configuration file. See the [CLI reference](../reference/cli.md).

## Verify

After deploying, before cutting DNS over:

```bash
hop3 app status --app myapp
hop3 app logs --app myapp
hop3 env show --app myapp --sources
hop3 app check --app myapp
```

`hop3 app check` is the one that matters: it runs the app's own smoke test, which signs in through the app's authentication rather than asking for a status code.

## Per-platform guides

### Heroku-style PaaS

- [From Heroku](migration/from-heroku.md)
- [From Render](migration/from-render.md)
- [From Railway](migration/from-railway.md)
- [From Fly.io](migration/from-fly-io.md)
- [From Scalingo](migration/from-scalingo.md)
- [From Clever Cloud](migration/from-clever-cloud.md)
- [From Platform.sh / Upsun](migration/from-platform-sh.md)
- [From DigitalOcean App Platform](migration/from-digitalocean-app-platform.md)

### Self-hosted PaaS

- [From Dokku](migration/from-dokku.md) — the closest cousin
- [From Piku](migration/from-piku.md)
- [From CapRover](migration/from-caprover.md)
- [From Coolify](migration/from-coolify.md)

### Containers and orchestration

- [From Kubernetes / k3s](migration/from-kubernetes.md)
- [From Docker Compose](migration/from-docker-compose.md)

### Frontend and Jamstack

- [From Vercel](migration/from-vercel.md)
- [From Netlify](migration/from-netlify.md)

### Hyperscaler app services

- [From Google Cloud Run](migration/from-cloud-run.md)
- [From Google App Engine](migration/from-google-app-engine.md)
- [From AWS Elastic Beanstalk](migration/from-elastic-beanstalk.md)
- [From Azure App Service](migration/from-azure-app-service.md)

### Scripts and hand-rolled deploys

- [From a hand-managed VPS](migration/from-vps.md)
- [From Capistrano](migration/from-capistrano.md)

Coming from something not listed? The method above still applies, and [an issue](https://github.com/abilian/hop3/issues) telling us what you moved from is how the list grows.

## Migrating between Hop3 versions

Moving from Hop3's pre-0.5 colon-syntax CLI (`hop3 config:set`) to the current space-separated commands is a different exercise: see [CLI Migration](cli-migration.md).

## Need help?

- [hop3.toml Reference](../reference/config.md)
- [Troubleshooting](troubleshooting.md)
- [FAQ](faq.md)
- [GitHub Issues](https://github.com/abilian/hop3/issues)
