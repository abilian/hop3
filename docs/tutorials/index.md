# Tutorials

Step-by-step guides for deploying web applications on Hop3. Each tutorial walks you through creating and deploying a simple application using a specific framework.

## What You'll Learn

Every tutorial follows a consistent pattern:

1. **Create** a minimal application with the framework
2. **Configure** the app for Hop3 deployment (hop3.toml, Procfile)
3. **Deploy** to your Hop3 server
4. **Verify** the application is running

## Choose Your Stack

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
| [Astro](javascript/astro.md) | Static site builder with islands |
| [Eleventy](javascript/eleventy.md) | Simple static site generator |
| [NestJS](javascript/nestjs.md) | Progressive Node.js framework |

### Go

| Framework | Description |
|-----------|-------------|
| [Gin](go/gin.md) | HTTP web framework |
| [Fiber](go/fiber.md) | Express-inspired web framework |
| [Hugo](go/hugo.md) | Static site generator |

### Ruby

| Framework | Description |
|-----------|-------------|
| [Rails](ruby/rails.md) | Full-stack web framework |
| [Sinatra](ruby/sinatra.md) | Lightweight DSL for web apps |
| [Jekyll](ruby/jekyll.md) | Static site generator |

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

## Prerequisites

Before starting any tutorial, ensure you have:

- A Hop3 server set up and accessible
- The `hop3` CLI installed and configured
- SSH access to your server (or local Docker for testing)

See the [Installation Guide](../get-started/server-setup.md) to get started.

## Common Configuration Files

All Hop3 applications use these configuration files:

### hop3.toml

The main configuration file that tells Hop3 how to build and run your app:

```toml
[app]
name = "myapp"

[web]
port = 5000
```

### Procfile

Defines how to start your application:

```procfile
web: python app.py
```

See the [Configuration Reference](../reference/config.md) for all available options.
