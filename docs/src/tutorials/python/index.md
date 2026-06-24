# Deploying Python on Hop3

Deploying a Python web app on Hop3 follows the same shape regardless of framework: you commit your code and a `requirements.txt`, declare how to start the server in `hop3.toml` (or a `Procfile`), and run `hop3 deploy`. Hop3 detects the Python toolchain, builds an isolated virtualenv from your requirements, then starts your app as a long-running process bound to a dynamic `$PORT` and fronted by nginx. There is no Docker required and no platform-specific SDK — your app reads its configuration from environment variables, exactly as it would on any twelve-factor host.

This page covers the concepts every Python tutorial in this section shares. Read it first, then follow the guide for your framework.

## How Hop3 builds and runs Python

Hop3's Python toolchain is auto-detected from your project (a `requirements.txt`, `pyproject.toml`, or `setup.py`). On each deploy it creates a fresh virtualenv and installs your dependencies into it; the `local` builder is the default, so no container is involved. System packages your wheels need to compile against (for example `libpq-dev` for `psycopg2`, or `gcc`/`python3-dev` for C extensions) are declared under `[build] packages` and installed before the build runs.

Your app is then run as a managed process. Hop3 assigns a port at runtime and exports it as the `$PORT` environment variable; your server **must** bind to `0.0.0.0:$PORT`. nginx is configured automatically as a reverse proxy in front of that process — it terminates the public hostname (set via `HOST_NAME`) and forwards requests to your app on `$PORT`. You never write nginx config yourself.

A representative `hop3.toml` for a Python app looks like this:

```toml
[metadata]
id = "my-python-app"
version = "1.0.0"
title = "My Python Application"

[build]
packages = ["python3", "python3-pip", "python3-venv"]

[run]
start = "gunicorn wsgi:app --bind 0.0.0.0:$PORT --workers 2 --threads 4"
before-run = "alembic upgrade head"   # optional: migrations, etc.

[env]
PYTHONUNBUFFERED = "1"

[port]
web = 8000

[healthcheck]
path = "/up"
timeout = 30
interval = 60
```

The only line that really changes between frameworks is `[run] start` — the command that launches your server bound to `$PORT`. A one-line `Procfile` (`web: gunicorn wsgi:app --bind 0.0.0.0:$PORT`) is equivalent and Heroku-compatible; you can use either or both. When both declare the same process, `hop3.toml` wins.

## WSGI vs ASGI: pick the right server

The single most important distinction in Python web deployment is whether your framework speaks **WSGI** (synchronous) or **ASGI** (asynchronous), because it decides which application server you launch in `[run] start`:

- **WSGI** (Flask, Django, Bottle, Falcon, Pyramid) — run under **Gunicorn**: `gunicorn wsgi:app --bind 0.0.0.0:$PORT --workers 2 --threads 4`.
- **ASGI** (FastAPI, Litestar, Starlette, Sanic) — run under **Uvicorn**: `uvicorn main:app --host 0.0.0.0 --port $PORT --workers 2`. For better process management you can run Uvicorn workers under Gunicorn: `gunicorn main:app --bind 0.0.0.0:$PORT --workers 2 --worker-class uvicorn.workers.UvicornWorker`.

Add `gunicorn` or `uvicorn` to your `requirements.txt` accordingly. The development server (`flask run`, `python app.py`, `uvicorn` reload mode) is never used in production.

## Cross-cutting notes

These apply to every framework here:

- **Configuration via environment.** Set values with `hop3 env set --app <app> KEY=value`. `HOST_NAME` defines the public hostname nginx serves. App-internal secrets like `SECRET_KEY` are declared in `hop3.toml` `[env]` as `SECRET_KEY = { generate = "hex", length = 32 }` — generated once on the first deploy and never committed; use `hop3 env set` only for secrets you supply yourself (API keys).
- **Databases and caches are addons.** Create and attach a service, and Hop3 injects its connection string for you: PostgreSQL exposes `DATABASE_URL`, Redis exposes `REDIS_URL`. Read them with `os.environ` and never hardcode credentials.

  ```bash
  hop3 addons create postgres my-app-db
  hop3 addons attach my-app my-app-db
  ```
- **Run setup before the web process starts.** Use `[run] before-run` (or a `prerun:` line in the `Procfile`) for database migrations and `collectstatic` — these run on every deploy before the new process takes traffic.
- **Health checks.** Expose a cheap endpoint (the tutorials use `/up` returning `OK`) and point `[healthcheck] path` at it so Hop3 knows when your app is ready.
- **One-off and background processes.** Run management commands in the app's environment with `hop3 run --app <app> <command>` (e.g. `python manage.py migrate`). Background workers (Celery, etc.) are declared as additional processes and scaled with `hop3 ps scale`.
- **Build caching.** Dependencies are reinstalled into the virtualenv on deploy; keep `requirements.txt` pinned and minimal for fast, reproducible builds.

## Choose a framework

| Framework | Model | Description |
|-----------|-------|-------------|
| [Flask](flask.md) | WSGI | The classic micro-framework — minimal, run under Gunicorn. |
| [Django](django.md) | WSGI | Batteries-included framework with ORM, admin, and migrations. |
| [FastAPI](fastapi.md) | ASGI | Async API framework with automatic OpenAPI docs, run under Uvicorn. |
| [Litestar](litestar.md) | ASGI | Modern async framework with strong typing and DI. |
| [Starlette](starlette.md) | ASGI | Lightweight async toolkit that FastAPI is built on. |
| [Bottle](bottle.md) | WSGI | Single-file micro-framework with zero dependencies. |
| [Falcon](falcon.md) | WSGI | Minimalist, high-performance framework for REST APIs. |
| [Eve](eve.md) | WSGI | REST API framework built on Flask, powered by MongoDB. |
| [DRF](drf.md) | WSGI | Django REST Framework — full-featured APIs on top of Django. |
| [Pyramid](pyramid.md) | WSGI | Flexible framework that scales from micro to large apps. |
| [Sanic](sanic.md) | ASGI | Async framework with its own fast built-in server. |
| [Robyn](robyn.md) | ASGI | Async framework with a Rust runtime for high throughput. |

Pick the framework you are building with; each guide is a complete, runnable walkthrough from project creation to a verified deployment.
