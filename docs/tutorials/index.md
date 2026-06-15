# Tutorials

Step-by-step guides for deploying web applications on Hop3. Each tutorial walks you through creating and deploying a small application with a specific framework — but they all share the same deployment model, so it is worth understanding the general principles first.

## How deployment works

Every tutorial follows the same four steps:

1. **Create** a minimal application with the framework.
2. **Configure** it for Hop3 (a `hop3.toml`, and/or a `Procfile`).
3. **Deploy** it to your Hop3 server (`hop3 deploy <app>`).
4. **Verify** it is running (`hop3 app status`, then open it in a browser).

Under the hood, Hop3 does the same thing for every app, whatever the language:

- **Builds** it with an auto-detected toolchain — Python virtualenv, Node/npm, Go, Ruby/Bundler, and so on. No Dockerfile is required (though you can use one).
- **Runs** it as a supervised process that listens on a **dynamic `$PORT`**. Your app must read `$PORT` and bind to it — a hardcoded port will not receive traffic. (Static sites are the exception: nginx serves their files directly, with no process — see [Static Sites](static/index.md).)
- **Proxies** it through nginx, which routes requests to your app by hostname (`HOST_NAME`) and terminates TLS, so many apps share ports 80/443.
- **Wires addons** (PostgreSQL, Redis, …) by injecting connection strings as environment variables such as `DATABASE_URL` and `REDIS_URL` — no host/port plumbing on your side.

Set configuration with `hop3 config set --app <app> KEY=value` — the most important is `HOST_NAME`, which tells nginx which domain to serve. App-internal secrets like `SECRET_KEY` are best **declared** in `hop3.toml` `[env]` as `{ generate = ... }`, so Hop3 creates them on the first deploy and never commits them; reserve `hop3 config set` for secrets you supply yourself (API keys).

## Prerequisites

Before starting any tutorial, ensure you have:

- A Hop3 server set up and accessible.
- The `hop3` CLI installed and configured.
- SSH access to your server (or local Docker for testing).

See the [Installation Guide](../get-started/server-setup.md) to get started.

## Configuration files

A Hop3 app is described by one or both of these files at the repository root:

### hop3.toml

The Hop3-specific configuration file — how to build and run your app. A minimal example:

```toml
[metadata]
id = "myapp"

[run]
start = "gunicorn app:app -b 0.0.0.0:$PORT"
```

Hop3 auto-detects the language toolchain from your project files; add a `[build]` section only when you need explicit build steps (e.g. `before-build = ["npm run build"]`). See the [Configuration Reference](../reference/config.md) for every option.

### Procfile

A generic, cross-tool process file. Hop3 reads it too, but `hop3.toml` takes precedence when both declare the same thing:

```procfile
web: gunicorn app:app -b 0.0.0.0:$PORT
```

## Choose Your Stack

With the model above in mind, pick your framework. Each section starts with an **overview** of how that language is built and run on Hop3, followed by framework-specific tutorials.

### Python

| Framework | Description |
|-----------|-------------|
| [Flask](python/flask.md) | Lightweight micro-framework |
| [Django](python/django.md) | Full-featured web framework |
| [FastAPI](python/fastapi.md) | Modern async API framework |
| [Litestar](python/litestar.md) | High-performance ASGI framework |
| [Starlette](python/starlette.md) | Lightweight ASGI toolkit |
| [Bottle](python/bottle.md) | Simple single-file micro-framework |
| [Falcon](python/falcon.md) | Minimalist REST API framework |
| [Eve](python/eve.md) | REST API framework built on Flask |
| [DRF](python/drf.md) | Django REST Framework |
| [Pyramid](python/pyramid.md) | Flexible, scalable framework |
| [Sanic](python/sanic.md) | Async web server and framework |
| [Robyn](python/robyn.md) | Fast async Python web framework |

### JavaScript / Node.js

| Framework | Description |
|-----------|-------------|
| [Express](javascript/express.md) | Minimal and flexible Node.js framework |
| [Fastify](javascript/fastify.md) | Fast and low-overhead framework |
| [Next.js](javascript/nextjs.md) | React framework with SSR |
| [Nuxt.js](javascript/nuxtjs.md) | Vue.js framework with SSR |
| [NestJS](javascript/nestjs.md) | Progressive Node.js framework |

### Go

| Framework | Description |
|-----------|-------------|
| [Gin](go/gin.md) | HTTP web framework |
| [Fiber](go/fiber.md) | Express-inspired web framework |

### Ruby

| Framework | Description |
|-----------|-------------|
| [Rails](ruby/rails.md) | Full-stack web framework |
| [Sinatra](ruby/sinatra.md) | Lightweight DSL for web apps |

### Rust

| Framework | Description |
|-----------|-------------|
| [Axum](rust/axum.md) | Ergonomic and modular framework |
| [Actix-web](rust/actix-web.md) | Powerful async framework |

### Java

| Framework | Description |
|-----------|-------------|
| [Spring Boot](java/spring-boot.md) | Production-ready Java framework |
| [Quarkus](java/quarkus.md) | Kubernetes-native Java framework |

### PHP

| Framework | Description |
|-----------|-------------|
| [Laravel](php/laravel.md) | Elegant PHP framework |
| [Symfony](php/symfony.md) | Flexible PHP framework |

### Elixir

| Framework | Description |
|-----------|-------------|
| [Phoenix](elixir/phoenix.md) | Productive web framework |

### .NET

| Framework | Description |
|-----------|-------------|
| [ASP.NET Core](dotnet/aspnet-core.md) | Cross-platform web framework |

### Static Sites

Sites served directly by nginx with no application process. Start with the [Static Sites overview](static/index.md), which explains the two deployment strategies (build at the source vs. build on the server).

| Guide | Description |
|-------|-------------|
| [Plain static site](static/static-site.md) | Pre-built HTML/CSS/JS served directly by nginx — no build, no app server |
| [Hugo](static/hugo.md) | Fast static site generator (Go) |
| [Astro](static/astro.md) | Modern static site builder (Node.js) |
| [Eleventy](static/eleventy.md) | Simple static site generator (Node.js) |
| [Jekyll](static/jekyll.md) | Blog-aware static site generator (Ruby) |
