# Deploying Ruby on Hop3

Deploying a Ruby web app on Hop3 means handing it a `Gemfile`, a Rack server, and a `hop3.toml` — Hop3 installs your gems with Bundler, boots your app under Puma bound to a dynamic port, and puts nginx in front of it. Whether you run a one-file Sinatra service or a full Rails 8 app with PostgreSQL and background jobs, the moving parts are the same; only the framework's conventions differ.

This page covers what every Ruby deployment has in common. Read it first, then follow the framework guide below that matches your app.

## How Hop3 builds and runs Ruby

Hop3 detects a Ruby app from its `Gemfile` and uses the Ruby toolchain to build it:

1. **Install gems** — Hop3 runs `bundle install` for you. You do *not* put this in `before-build`; the toolchain handles it. Use `before-build` only for steps that come *after* gems are installed, such as `bin/rails assets:precompile`.
2. **Run extra build steps** — anything in `[build] before-build` runs next (asset compilation, etc.). System packages your gems need to compile native extensions go in `[build] packages` (e.g. `postgresql-dev`, `nodejs`).
3. **Start the process** — Hop3 runs your `[run] start` command. This must launch a **Rack server** (Puma in both guides) that **binds to the `$PORT` environment variable Hop3 assigns** — never a hard-coded port. Your `config/puma.rb` should read it: `port ENV.fetch("PORT", 3000)`.
4. **Proxy through nginx** — Hop3 configures nginx to forward your app's public hostname (`HOST_NAME`) to the process on `$PORT`. Because nginx terminates the request, disable Rack's host/origin protection (`disable :protection` in Sinatra) so you don't get "Host not permitted" errors behind the proxy.

A representative Ruby `hop3.toml`:

```toml
[metadata]
id = "my-ruby-app"
version = "1.0.0"

[build]
# bundle install is automatic; list extra steps and system packages here
before-build = ["bin/rails assets:precompile"]
packages = ["postgresql-dev", "nodejs"]

[run]
start = "bundle exec puma -C config/puma.rb"
before-run = "bin/rails db:migrate"   # runs once before the web process starts

[port]
web = 3000        # the port your app listens on locally; Hop3 maps it via $PORT

[healthcheck]
path = "/up"

[[provider]]
name = "postgres"
plan = "standard"
```

The `[port] web` value is the conventional port for the framework (3000 for Rails, 4567 for Sinatra); Hop3 still injects `$PORT` at runtime, so always read it in your Puma config rather than trusting the default.

## Notes that apply to every Ruby framework

- **Puma + a `config/puma.rb`.** Both guides run `bundle exec puma -C config/puma.rb`. Keep worker and thread counts driven by env vars (`WEB_CONCURRENCY`, `RAILS_MAX_THREADS`) so you can scale without code changes.
- **Health checks.** Expose a cheap endpoint (Rails 8 ships `/up`; Sinatra defines one) and point `[healthcheck] path` at it so Hop3 knows when the app is live.
- **Addons inject env vars.** Attach a `postgres` provider and Hop3 sets `DATABASE_URL`; attach `redis` and it sets `REDIS_URL`. Read those in `config/database.yml` and your job/cable config — never hard-code connection strings.
- **Migrations and pre-run hooks.** Put schema migrations in `[run] before-run` (or a `prerun:` line in a `Procfile`) so they run once per deploy before the web process boots.
- **Logs to stdout.** Hop3 captures the process's stdout/stderr. For Rails, set `RAILS_LOG_TO_STDOUT=true`; let `hop3 app logs --app <app>` show you everything.
- **Secrets via config, not in git.** Declare `SECRET_KEY_BASE = { generate = "hex", length = 64 }` in `hop3.toml` `[env]` so Hop3 generates it on the first deploy — never committed. Keep `config/master.key` and credentials out of the repo; use `hop3 env set` for secrets you supply yourself.
- **Procfile vs. hop3.toml.** Either works for declaring processes; when both exist, `hop3.toml` wins. The guides show both styles — pick one and stay consistent.

## Choose a framework

| Framework | Use it for |
|-----------|------------|
| [Rails](rails.md) | Full-stack Rails 8 apps — PostgreSQL via `DATABASE_URL`, asset precompilation, migrations, and optional Sidekiq/Solid Queue workers and Action Cable. |
| [Sinatra](sinatra.md) | Lightweight services and JSON APIs — a single `app.rb`, a tiny `Gemfile`, Puma, and a `config.ru` for Rack. |

Jekyll, a Ruby *static-site generator*, is documented under [Static Sites](../static/index.md) rather than here, since Hop3 serves its output directly through nginx with no running process.
