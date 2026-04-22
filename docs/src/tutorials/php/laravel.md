# Deploying Laravel on Hop3

This guide walks you through deploying a Laravel application on Hop3. By the end, you'll have a production-ready PHP application running on your own infrastructure.

## Prerequisites

Before you begin, ensure you have:

1. **A Hop3 server** - Follow the [Installation Guide](../../get-started/installation.md) if you haven't set one up yet
2. **The Hop3 CLI** - Installed on your local machine
3. **PHP 8.2+** - Install via your package manager or [php.net](https://www.php.net/)
4. **Composer** - PHP dependency manager from [getcomposer.org](https://getcomposer.org/)
5. **Git** - For version control and deployment

Verify your local setup:

```bash
php -v
```

```bash
composer --version
```

## Step 1: Create a New Laravel Application

Create a new Laravel application using Composer:

```bash
composer create-project laravel/laravel hop3-tuto-laravel --no-interaction
```

Verify the project structure:

```bash
ls -la
```

```console
artisan
```

```console
composer.json
```

```console
app
```

## Step 2: Configure the Application

### Generate Application Key

Generate the application encryption key:

```bash
php artisan key:generate
```

```console
Application key set successfully
```

### Create Welcome Route

Laravel comes with a welcome page. Let's add a health check route. Edit `routes/web.php`:

```php
<?php

use Illuminate\Support\Facades\Route;

Route::get('/', function () {
    return view('welcome');
});

// Health check endpoint for Hop3
Route::get('/up', function () {
    return response('OK', 200);
});

Route::get('/health', function () {
    try {
        \DB::connection()->getPdo();
        $dbStatus = 'connected';
    } catch (\Exception $e) {
        $dbStatus = 'disconnected';
    }

    return response()->json([
        'status' => 'ok',
        'php_version' => PHP_VERSION,
        'laravel_version' => app()->version(),
        'database' => $dbStatus,
    ]);
});
```

### Create Custom Welcome View

Create a custom welcome page:

```php
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Welcome to Hop3</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            margin: 0;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
        }
        .container {
            text-align: center;
            padding: 2rem;
        }
        h1 {
            font-size: 3rem;
            margin-bottom: 1rem;
        }
        p {
            font-size: 1.25rem;
            opacity: 0.9;
        }
        .info {
            margin-top: 2rem;
            padding: 1rem;
            background: rgba(255,255,255,0.1);
            border-radius: 8px;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>Hello from Hop3!</h1>
        <p>Your Laravel application is running.</p>
        <div class="info">
            <p>Laravel {{ app()->version() }} | PHP {{ PHP_VERSION }}</p>
            <p>Time: {{ now() }}</p>
        </div>
    </div>
</body>
</html>
```

## Step 3: Configure for Production

### Configure Environment Variables

Laravel uses a `.env` file for configuration. Create a production-ready template:

```bash
APP_NAME=MyApp
APP_ENV=production
APP_KEY=
APP_DEBUG=false
APP_URL=http://localhost

LOG_CHANNEL=stderr
LOG_LEVEL=info

DB_CONNECTION=pgsql
DB_HOST=127.0.0.1
DB_PORT=5432
DB_DATABASE=hop3-tuto-laravel
DB_USERNAME=hop3-tuto-laravel
DB_PASSWORD=

SESSION_DRIVER=file
SESSION_LIFETIME=120

CACHE_DRIVER=file
QUEUE_CONNECTION=sync
```

### Configure Database for Production

Update `config/database.php` to read from `DATABASE_URL`:

```bash
grep -l "DATABASE_URL" config/database.php || echo "Need to configure DATABASE_URL"
```

Create a production database configuration:

```php
<?php

use Illuminate\Support\Str;

// Parse DATABASE_URL if provided
$databaseUrl = env('DATABASE_URL');
$dbConfig = [];

if ($databaseUrl) {
    $dbConfig = parse_url($databaseUrl);
    $dbConfig['database'] = ltrim($dbConfig['path'] ?? '', '/');
}

return [
    'default' => env('DB_CONNECTION', 'pgsql'),

    'connections' => [
        'sqlite' => [
            'driver' => 'sqlite',
            'url' => env('DATABASE_URL'),
            'database' => env('DB_DATABASE', database_path('database.sqlite')),
            'prefix' => '',
            'foreign_key_constraints' => env('DB_FOREIGN_KEYS', true),
        ],

        'pgsql' => [
            'driver' => 'pgsql',
            'url' => env('DATABASE_URL'),
            'host' => $dbConfig['host'] ?? env('DB_HOST', '127.0.0.1'),
            'port' => $dbConfig['port'] ?? env('DB_PORT', '5432'),
            'database' => $dbConfig['database'] ?? env('DB_DATABASE', 'forge'),
            'username' => $dbConfig['user'] ?? env('DB_USERNAME', 'forge'),
            'password' => $dbConfig['pass'] ?? env('DB_PASSWORD', ''),
            'charset' => 'utf8',
            'prefix' => '',
            'prefix_indexes' => true,
            'search_path' => 'public',
            'sslmode' => 'prefer',
        ],

        'mysql' => [
            'driver' => 'mysql',
            'url' => env('DATABASE_URL'),
            'host' => env('DB_HOST', '127.0.0.1'),
            'port' => env('DB_PORT', '3306'),
            'database' => env('DB_DATABASE', 'forge'),
            'username' => env('DB_USERNAME', 'forge'),
            'password' => env('DB_PASSWORD', ''),
            'unix_socket' => env('DB_SOCKET', ''),
            'charset' => 'utf8mb4',
            'collation' => 'utf8mb4_unicode_ci',
            'prefix' => '',
            'prefix_indexes' => true,
            'strict' => true,
            'engine' => null,
        ],
    ],

    'migrations' => 'migrations',

    'redis' => [
        'client' => env('REDIS_CLIENT', 'phpredis'),
        'options' => [
            'cluster' => env('REDIS_CLUSTER', 'redis'),
            'prefix' => env('REDIS_PREFIX', Str::slug(env('APP_NAME', 'laravel'), '_').'_database_'),
        ],
        'default' => [
            'url' => env('REDIS_URL'),
            'host' => env('REDIS_HOST', '127.0.0.1'),
            'username' => env('REDIS_USERNAME'),
            'password' => env('REDIS_PASSWORD'),
            'port' => env('REDIS_PORT', '6379'),
            'database' => env('REDIS_DB', '0'),
        ],
        'cache' => [
            'url' => env('REDIS_URL'),
            'host' => env('REDIS_HOST', '127.0.0.1'),
            'username' => env('REDIS_USERNAME'),
            'password' => env('REDIS_PASSWORD'),
            'port' => env('REDIS_PORT', '6379'),
            'database' => env('REDIS_CACHE_DB', '1'),
        ],
    ],
];
```

### Configure Logging for Production

Update logging to use stderr (captured by Hop3):

```bash
sed -i.bak "s/LOG_CHANNEL=stack/LOG_CHANNEL=stderr/" .env 2>/dev/null || true
```

### Create Storage Directories

Ensure storage directories exist:

```bash
mkdir -p storage/app/public storage/framework/cache storage/framework/sessions storage/framework/views bootstrap/cache
chmod -R 775 storage bootstrap/cache
```

## Step 4: Verify the Application Works

Run Laravel's built-in checks:

```bash
php artisan about | head -20
```

```console
Laravel
```

Verify routes are registered:

```bash
grep -c "Route::get" routes/web.php
```

```console
3
```

## Step 5: Create Deployment Configuration

### Create a Procfile

Create a `Procfile` in your project root:

```procfile
# Pre-build: Install dependencies and optimize
prebuild: composer install --no-dev --optimize-autoloader

# Pre-run: Run migrations and cache config
prerun: php artisan migrate --force && php artisan config:cache && php artisan route:cache && php artisan view:cache

# Main web process
web: php artisan serve --host=0.0.0.0 --port=$PORT
```

!!! tip "Production Server"
    For production, consider using PHP-FPM with Nginx or Laravel Octane for better performance. The built-in server is used here for simplicity.

### Create hop3.toml

Create a `hop3.toml` for advanced configuration:

```toml
[metadata]
id = "hop3-tuto-laravel"
version = "1.0.0"
title = "My Laravel Application"

[build]
before-build = [
    "composer install --no-dev --optimize-autoloader"
]
packages = ["php", "php-pgsql", "php-mbstring", "php-xml", "php-curl", "composer"]

[run]
start = "php artisan serve --host=0.0.0.0 --port=$PORT"
before-run = "php artisan migrate --force && php artisan config:cache && php artisan route:cache"

[env]
APP_ENV = "production"
APP_DEBUG = "false"
LOG_CHANNEL = "stderr"

[port]
web = 8000

[healthcheck]
path = "/up"
timeout = 30
interval = 60

[[provider]]
name = "postgres"
plan = "standard"
```

Verify the deployment files exist:

```bash
ls -la Procfile hop3.toml
```

```console
Procfile
```

```console
hop3.toml
```

## Step 6: Initialize Git Repository

Update the `.gitignore` file:

```text
/node_modules
/public/build
/public/hot
/public/storage
/storage/*.key
/vendor
.env
.env.backup
.env.production
.phpunit.result.cache
Homestead.json
Homestead.yaml
auth.json
npm-debug.log
yarn-error.log
/.fleet
/.idea
/.vscode
/.vagrant
.DS_Store
```

Initialize the repository:

```bash
git init
```

```console
Initialized empty Git repository
```

```bash
git add .
```

```bash
git commit -m "Initial Laravel application"
```

```console
Initial Laravel application
```

## Step 7: Deploy to Hop3

The following steps require a Hop3 server. Set the `HOP3_SERVER` environment variable to your server address before running these commands.

### Configure the CLI

If this is your first deployment, initialize Hop3:

```bash
hop3 init --ssh root@your-server.example.com
```

### Create and Attach a Database

```bash
hop3 addons create postgres hop3-tuto-laravel-db
hop3 addons attach hop3-tuto-laravel hop3-tuto-laravel-db
```

### Set Environment Variables

```bash
# Generate and set the application key
hop3 config set --app hop3-tuto-laravel APP_KEY=$(php artisan key:generate --show)

# Set Laravel environment variables
hop3 config set --app hop3-tuto-laravel APP_ENV=production
hop3 config set --app hop3-tuto-laravel APP_DEBUG=false
hop3 config set --app hop3-tuto-laravel LOG_CHANNEL=stderr
```

### Prepare for Deployment

Remove files that cause deployment issues:
- `composer.lock` - avoids PHP version conflicts between local and server
- `package.json` - prevents multi-language detection (Vite not needed for basic deployment)

```bash
rm -f composer.lock package.json package-lock.json vite.config.js
git add -A && git commit -m "Prepare for deployment" || true
```

### Deploy

Deploy the application (first deployment creates the app):

```bash
hop3 deploy hop3-tuto-laravel
```

### Set Hostname

Configure the hostname for nginx proxy:

```bash
hop3 config set --app hop3-tuto-laravel HOST_NAME=hop3-tuto-laravel.$HOP3_TEST_DOMAIN
```

### Apply Configuration

Redeploy to apply the hostname configuration:

```bash
hop3 deploy hop3-tuto-laravel
```

Wait for the application to start:

```bash
sleep 5
```

You'll see output showing:
- Code upload
- Dependency installation (`composer install`)
- Database migration
- Configuration caching
- Application startup

## Step 8: Verify Deployment

Check your application status:

```bash
hop3 status --app hop3-tuto-laravel
```

```console
hop3-tuto-laravel

```bash
curl -s http://hop3-tuto-laravel.$HOP3_TEST_DOMAIN/up
```

```console
OK
``````

View logs:

```bash
hop3 logs --app hop3-tuto-laravel
```

Open your application:

```bash
# Your app will be available at:
# http://hop3-tuto-laravel.your-hop3-server.example.com
```

## Managing Your Application

### Run Artisan Commands

```bash
hop3 run hop3-tuto-laravel php artisan migrate
hop3 run hop3-tuto-laravel php artisan tinker
hop3 run hop3-tuto-laravel php artisan queue:work --once
```

### Clear Caches

```bash
hop3 run hop3-tuto-laravel php artisan cache:clear
hop3 run hop3-tuto-laravel php artisan config:clear
hop3 run hop3-tuto-laravel php artisan route:clear
hop3 run hop3-tuto-laravel php artisan view:clear
```

### View and Manage Environment Variables

```bash
# List all variables
hop3 config show --app hop3-tuto-laravel

# Set a variable
hop3 config set --app hop3-tuto-laravel MAIL_MAILER=smtp

# Remove a variable
hop3 config unset --app hop3-tuto-laravel OLD_VARIABLE
```

### Scaling

```bash
# Check current processes
hop3 ps hop3-tuto-laravel

# Scale web workers
hop3 ps scale --app hop3-tuto-laravel web=2
```

## Advanced Configuration

### Using Laravel Octane for Better Performance

Laravel Octane can significantly improve performance using Swoole or RoadRunner:

```bash
composer require laravel/octane
php artisan octane:install --server=frankenphp
```

Update `Procfile`:

```procfile
web: php artisan octane:start --server=frankenphp --host=0.0.0.0 --port=$PORT
```

### Queue Workers

Add a queue worker to your `Procfile`:

```procfile
web: php artisan serve --host=0.0.0.0 --port=$PORT
worker: php artisan queue:work --sleep=3 --tries=3 --max-time=3600
```

Configure queue connection:

```bash
hop3 config set --app hop3-tuto-laravel QUEUE_CONNECTION=database
```

### Scheduled Tasks

Add a scheduler worker:

```procfile
scheduler: while true; do php artisan schedule:run --verbose --no-interaction; sleep 60; done
```

Or use cron in `hop3.toml`:

```toml
[cron]
schedule = "* * * * * php artisan schedule:run >> /dev/null 2>&1"
```

### Redis for Cache and Sessions

Install Redis support:

```bash
composer require predis/predis
```

Attach Redis addon:

```bash
hop3 addons create redis hop3-tuto-laravel-redis
hop3 addons attach hop3-tuto-laravel hop3-tuto-laravel-redis
hop3 config set --app hop3-tuto-laravel CACHE_DRIVER=redis
hop3 config set --app hop3-tuto-laravel SESSION_DRIVER=redis
```

### File Storage with S3

For file uploads using S3-compatible storage:

```bash
composer require league/flysystem-aws-s3-v3
```

Configure in `config/filesystems.php` and set:

```bash
hop3 config set --app hop3-tuto-laravel FILESYSTEM_DISK=s3
hop3 config set --app hop3-tuto-laravel AWS_ACCESS_KEY_ID=your-key
hop3 config set --app hop3-tuto-laravel AWS_SECRET_ACCESS_KEY=your-secret
hop3 config set --app hop3-tuto-laravel AWS_DEFAULT_REGION=us-east-1
hop3 config set --app hop3-tuto-laravel AWS_BUCKET=your-bucket
```

### Mail Configuration

Configure mail using environment variables:

```bash
hop3 config set --app hop3-tuto-laravel MAIL_MAILER=smtp
hop3 config set --app hop3-tuto-laravel MAIL_HOST=smtp.mailgun.org
hop3 config set --app hop3-tuto-laravel MAIL_PORT=587
hop3 config set --app hop3-tuto-laravel MAIL_USERNAME=your-username
hop3 config set --app hop3-tuto-laravel MAIL_PASSWORD=your-password
hop3 config set --app hop3-tuto-laravel MAIL_ENCRYPTION=tls
```

## Troubleshooting

### Application Won't Start

Check the logs for errors:

```bash
hop3 logs --app hop3-tuto-laravel --tail
```

Common issues:
- **Missing APP_KEY**: Generate with `php artisan key:generate --show`
- **Database not connected**: Ensure the addon is attached
- **Missing PHP extensions**: Check required extensions in `composer.json`

### Permission Issues

Storage directories need write permissions:

```bash
hop3 run hop3-tuto-laravel chmod -R 775 storage bootstrap/cache
```

### Composer Memory Issues

If Composer runs out of memory:

```bash
hop3 config set --app hop3-tuto-laravel COMPOSER_MEMORY_LIMIT=-1
```

### Database Connection Issues

Verify the database is attached:

```bash
hop3 config show --app hop3-tuto-laravel | grep DATABASE
```

Test the connection:

```bash
hop3 run hop3-tuto-laravel php artisan db:show
```

### Asset Compilation Issues

If using Vite or Mix:

```bash
# Add to build step
npm install && npm run build
```

Update `hop3.toml`:

```toml
[build]
before-build = [
    "composer install --no-dev --optimize-autoloader",
    "npm install",
    "npm run build"
]
packages = ["php", "nodejs", "npm"]
```

## Next Steps

- **[CLI Reference](../../reference/cli.md)** - Complete command reference
- **[hop3.toml Reference](../../reference/config.md)** - Full configuration options
- **[Backup and Restore Guide](../../guides/backup-restore.md)** - Protect your data

## Example Files

### Complete hop3.toml for Laravel

```toml
# hop3.toml - Laravel Application

[metadata]
id = "hop3-tuto-laravel"
version = "1.0.0"
title = "My Laravel Application"
author = "Your Name <you@example.com>"

[build]
before-build = [
    "composer install --no-dev --optimize-autoloader",
    "npm install",
    "npm run build"
]
packages = ["php", "php-pgsql", "php-mbstring", "php-xml", "php-curl", "php-redis", "composer", "nodejs"]

[run]
start = "php artisan serve --host=0.0.0.0 --port=$PORT"
before-run = "php artisan migrate --force && php artisan config:cache && php artisan route:cache && php artisan view:cache"

[env]
APP_ENV = "production"
APP_DEBUG = "false"
LOG_CHANNEL = "stderr"

[port]
web = 8000

[healthcheck]
path = "/up"
timeout = 30
interval = 60

[backup]
enabled = true
schedule = "0 3 * * *"
retention = 14

[[provider]]
name = "postgres"
plan = "standard"

[[provider]]
name = "redis"
plan = "basic"
```

### Complete Procfile for Laravel

```procfile
# Procfile - Laravel Application

# Build phase
prebuild: composer install --no-dev --optimize-autoloader && npm install && npm run build

# Pre-run hooks (migrations and caching)
prerun: php artisan migrate --force && php artisan config:cache && php artisan route:cache && php artisan view:cache

# Web server
web: php artisan serve --host=0.0.0.0 --port=$PORT

# Queue worker (optional)
worker: php artisan queue:work --sleep=3 --tries=3 --max-time=3600

# Scheduler (optional)
scheduler: while true; do php artisan schedule:run; sleep 60; done
```
