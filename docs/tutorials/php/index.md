# Deploying PHP on Hop3

A PHP app on Hop3 is your project plus its `composer.json`: Hop3 installs the PHP runtime and Composer for you, runs `composer install` to fetch your dependencies, runs any framework warm-up step (migrations, cache priming), then starts a PHP web process bound to a port Hop3 hands it. Nginx sits in front and proxies your hostname to that process. You write almost no PHP-specific glue — the same `composer install` / `$PORT` / nginx pattern carries every framework below.

This page covers what is shared by every PHP deployment. Read it first, then follow the framework guide that matches your stack.

## How Hop3 builds and runs PHP

Hop3 detects a PHP app from its `composer.json`. You list the runtime and extensions you need in `[build].packages` (e.g. `php`, `composer`, plus extensions like `php-pgsql`, `php-mbstring`, `php-xml`, `php-intl`), and `[build].before-build` runs `composer install --no-dev --optimize-autoloader` to produce a `vendor/` directory.

The app is run as a long-lived web process bound to the dynamic port Hop3 injects as `$PORT`. Hop3 picks the port — your process must bind exactly to it on `0.0.0.0` — and nginx terminates the public hostname and proxies requests to that port. Any framework warm-up (database migrations, config/route/view caching) goes in `[run].before-run`, which runs once before the process starts.

A representative `hop3.toml` shared across PHP frameworks:

```toml
[metadata]
id = "my-php-app"
version = "1.0.0"

[build]
before-build = ["composer install --no-dev --optimize-autoloader"]
packages = ["php", "php-pgsql", "php-mbstring", "php-xml", "composer"]

[run]
start = "php -S 0.0.0.0:$PORT -t public"
before-run = "..."   # framework warm-up: migrations, cache priming

[env]
APP_ENV = "production"

[healthcheck]
path = "/up"
```

The `start` line is the one real difference between frameworks: a Symfony skeleton serves its `public/` document root with the built-in server (`php -S 0.0.0.0:$PORT -t public`), while Laravel uses `php artisan serve --host=0.0.0.0 --port=$PORT`. Both are fine for getting an app live; for heavier production traffic, move to PHP-FPM behind nginx or a runtime like Laravel Octane / FrankenPHP.

## Notes that apply to every PHP app

- **Document root is `public/`.** PHP frameworks put a single front controller (`index.php`) in `public/`; never expose the project root. The built-in server's `-t public` (or Laravel's `artisan serve`) enforces this.
- **Databases via addons.** Create and attach a Postgres or MySQL addon and Hop3 injects `DATABASE_URL` into the app's environment. Parse it in your framework config (Laravel reads it in `config/database.php`; Symfony's Doctrine reads `DATABASE_URL` directly). Declare the addon in `hop3.toml` with a `[[provider]]` block, then run migrations from `before-run`.
- **Secrets are config, not files.** Declare app-internal secrets in `hop3.toml` `[env]` so Hop3 generates them on the first deploy: `APP_KEY = { generate = "base64", length = 32, prefix = "base64:" }` (Laravel) or `APP_SECRET = { generate = "hex", length = 16 }` (Symfony) — never committed. Set non-secret config like `APP_ENV=production`/`prod` and `APP_DEBUG=false`/`0` in `[env]` too; use `hop3 config set` for secrets you supply yourself.
- **Logs go to stderr.** Point your framework's log channel at stderr (`LOG_CHANNEL=stderr` for Laravel) so `hop3 app logs` captures them.
- **Drop `composer.lock` before the first deploy** if your local PHP version differs from the server's — it avoids "platform requirements" install failures. Drop a stray `package.json` too unless you actually build front-end assets, so Hop3 doesn't try to run a Node build it doesn't need.
- **Writable directories.** Laravel needs `storage/` and `bootstrap/cache/` writable; Symfony needs `var/`. If you hit permission errors, fix them in `before-run` rather than by hand on the server.
- **Front-end assets** (Vite, Webpack Encore) are an opt-in extra step: add `npm install && npm run build` to `before-build` and `nodejs` to `packages`.

## Choose a framework

| Framework | Description |
|-----------|-------------|
| [Laravel](laravel.md) | Full-stack PHP framework; deployed with `php artisan serve`, migrations and config caching in `before-run`, Postgres/Redis via addons. |
| [Symfony](symfony.md) | Enterprise PHP framework; serves `public/` via the built-in PHP server, Doctrine reads `DATABASE_URL`, cache warmed in `before-run`. |
