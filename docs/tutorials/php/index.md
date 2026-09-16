# Deploying PHP on Hop3

A PHP app on Hop3 is your project plus its `composer.json`: Hop3 installs the PHP runtime and Composer for you, runs `composer install` to fetch your dependencies, runs any framework warm-up step (migrations, cache priming), then serves it with **php-fpm behind nginx**. You write almost no PHP-specific glue, and — unlike every other language on Hop3 — you do not write a start command at all.

This page covers what is shared by every PHP deployment. Read it first, then follow the framework guide that matches your stack.

## How Hop3 builds and runs PHP

Hop3 detects a PHP app from its `composer.json`. You list the runtime and extensions you need in `[build].packages` (e.g. `php`, `composer`, plus extensions like `php-pgsql`, `php-mbstring`, `php-xml`, `php-intl`), and `[build].before-build` runs `composer install --no-dev --optimize-autoloader` to produce a `vendor/` directory.

Then Hop3 runs a **php-fpm pool** for your app and points nginx at it over FastCGI. nginx serves your static files off disk and hands `.php` requests to the pool, with the usual front-controller fallback (`try_files … /index.php`), so framework routing works without configuration. There is no `[run].start` line: PHP's built-in server (`php -S`, and `php artisan serve` which wraps it) is a development server, single-threaded, and an app that makes an HTTP request to itself deadlocks on it. Any framework warm-up (database migrations, config/route/view caching) goes in `[run].before-run`, which runs once before the pool starts.

A representative `hop3.toml` shared across PHP frameworks:

```toml
[metadata]
id = "my-php-app"
version = "1.0.0"

[build]
before-build = ["composer install --no-dev --optimize-autoloader"]
packages = ["php", "php-pgsql", "php-mbstring", "php-xml", "composer"]

[run]
before-run = "..."   # framework warm-up: migrations, cache priming

[env]
APP_ENV = "production"

[healthcheck]
path = "/up"
```

Note what is not there: no `start`. That is the same file for Laravel, Symfony and a flat PHP project — the difference between frameworks used to live in a start command, and now it does not.

## Notes that apply to every PHP app

- **Document root is `public/`, and it is detected.** PHP frameworks put a single front controller (`index.php`) in `public/`; the project root must never be served, because that publishes your `.env`, your `composer.json` and your whole `vendor/` tree. Hop3 looks for a front controller in `public/`, `web/`, `htdocs/` and `www/`, in that order, and falls back to the project root only when there is none. If your web root is somewhere else, say so with `[build].document-root = "…"` — a path that does not exist is refused at deploy rather than quietly serving the wrong thing.
- **Databases via addons.** Create and attach a Postgres or MySQL addon and Hop3 injects `DATABASE_URL` into the app's environment. Parse it in your framework config (Laravel reads it in `config/database.php`; Symfony's Doctrine reads `DATABASE_URL` directly). Declare the addon in `hop3.toml` with a `[[provider]]` block, then run migrations from `before-run`.
- **Secrets are config, not files.** Declare app-internal secrets in `hop3.toml` `[env]` so Hop3 generates them on the first deploy: `APP_KEY = { generate = "base64", length = 32, prefix = "base64:" }` (Laravel) or `APP_SECRET = { generate = "hex", length = 16 }` (Symfony) — never committed. Set non-secret config like `APP_ENV=production`/`prod` and `APP_DEBUG=false`/`0` in `[env]` too; use `hop3 env set` for secrets you supply yourself.
- **Logs go to stderr.** Point your framework's log channel at stderr (`LOG_CHANNEL=stderr` for Laravel) so `hop3 app logs` captures them.
- **Drop `composer.lock` before the first deploy** if your local PHP version differs from the server's — it avoids "platform requirements" install failures. Drop a stray `package.json` too unless you actually build front-end assets, so Hop3 doesn't try to run a Node build it doesn't need.
- **Writable directories.** Laravel needs `storage/` and `bootstrap/cache/` writable; Symfony needs `var/`. If you hit permission errors, fix them in `before-run` rather than by hand on the server.
- **Front-end assets** (Vite, Webpack Encore) are an opt-in extra step: add `npm install && npm run build` to `before-build` and `nodejs` to `packages`.

## Choose a framework

| Framework | Description |
|-----------|-------------|
| [Laravel](laravel.md) | Full-stack PHP framework; migrations and config caching in `before-run`, Postgres/Redis via addons. |
| [Symfony](symfony.md) | Enterprise PHP framework; Doctrine reads `DATABASE_URL`, cache warmed in `before-run`. |
