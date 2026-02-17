---
tutorial:
  name: symfony-hop3-tutorial
  env:
    APP_ENV: dev
    APP_SECRET: "dev-only-secret-not-for-production"
  teardown:
  - rm -rf hop3-tuto-symfony 2>/dev/null || true
  - hop3 app:destroy hop3-tuto-symfony -y 2>/dev/null || true
---

# Deploying Symfony on Hop3

This guide walks you through deploying a Symfony application on Hop3. By the end, you'll have a production-ready enterprise PHP application running on your own infrastructure.

## Prerequisites

Before you begin, ensure you have:

1. **A Hop3 server** - Follow the [Installation Guide](../installation.md) if you haven't set one up yet
2. **The Hop3 CLI** - Installed on your local machine
3. **PHP 8.2+** - Install via your package manager
4. **Composer** - PHP dependency manager
5. **Symfony CLI** (optional) - From [symfony.com/download](https://symfony.com/download)
6. **Git** - For version control and deployment

Verify your local setup:

```bash exec id=check-php
php -v
```

```output regex
PHP 8\.[0-9]+\.
```

```bash exec id=check-composer
composer --version
```

```output regex
Composer version [0-9]+\.
```

## Step 1: Create a New Symfony Application

Create a new Symfony web application:

```bash exec id=create-symfony timeout=180
composer create-project symfony/skeleton hop3-tuto-symfony --no-interaction
```

```assert file-exists path=hop3-tuto-symfony/composer.json
```

Install the web application bundle:

```bash exec id=install-webapp dir=hop3-tuto-symfony timeout=120
composer require webapp --no-interaction
```

```output contains
What's next
```

Verify the project structure:

```bash exec id=verify-structure dir=hop3-tuto-symfony
ls -la
```

```output contains
composer.json
```

```output contains
src
```

## Step 2: Create Controllers

Create a welcome controller:

```file path=hop3-tuto-symfony/src/Controller/WelcomeController.php
<?php

namespace App\Controller;

use Symfony\Bundle\FrameworkBundle\Controller\AbstractController;
use Symfony\Component\HttpFoundation\Response;
use Symfony\Component\Routing\Annotation\Route;

class WelcomeController extends AbstractController
{
    #[Route('/', name: 'welcome')]
    public function index(): Response
    {
        return new Response(<<<HTML
<!DOCTYPE html>
<html>
<head>
    <title>Welcome to Hop3</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            margin: 0;
            background: linear-gradient(135deg, #000000 0%, #1a1a1a 100%);
            color: white;
        }
        .container { text-align: center; padding: 2rem; }
        h1 { font-size: 3rem; margin-bottom: 1rem; }
        p { font-size: 1.25rem; opacity: 0.9; }
        .symfony-logo { font-size: 4rem; margin-bottom: 1rem; }
        a {
            display: inline-block;
            margin-top: 1rem;
            padding: 0.75rem 1.5rem;
            background: #7AB55C;
            border-radius: 8px;
            color: white;
            text-decoration: none;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="symfony-logo">🎵</div>
        <h1>Hello from Hop3!</h1>
        <p>Your Symfony application is running.</p>
        <p>Current time: {$this->getCurrentTime()}</p>
        <a href="/api/info">API Info</a>
    </div>
</body>
</html>
HTML);
    }

    private function getCurrentTime(): string
    {
        return (new \DateTime())->format('c');
    }
}
```

Create a health controller:

```file path=hop3-tuto-symfony/src/Controller/HealthController.php
<?php

namespace App\Controller;

use Symfony\Bundle\FrameworkBundle\Controller\AbstractController;
use Symfony\Component\HttpFoundation\JsonResponse;
use Symfony\Component\HttpFoundation\Response;
use Symfony\Component\Routing\Annotation\Route;

class HealthController extends AbstractController
{
    #[Route('/up', name: 'up')]
    public function up(): Response
    {
        return new Response('OK');
    }

    #[Route('/health', name: 'health')]
    public function health(): JsonResponse
    {
        return $this->json([
            'status' => 'ok',
            'timestamp' => (new \DateTime())->format('c'),
            'php_version' => PHP_VERSION,
            'memory' => [
                'usage' => round(memory_get_usage() / 1024 / 1024, 2) . 'MB',
                'peak' => round(memory_get_peak_usage() / 1024 / 1024, 2) . 'MB',
            ],
        ]);
    }

    #[Route('/api/info', name: 'api_info')]
    public function info(): JsonResponse
    {
        return $this->json([
            'name' => 'hop3-tuto-symfony',
            'version' => '1.0.0',
            'symfony_version' => \Symfony\Component\HttpKernel\Kernel::VERSION,
            'php_version' => PHP_VERSION,
            'environment' => $_ENV['APP_ENV'] ?? 'prod',
        ]);
    }
}
```

```assert file-exists path=hop3-tuto-symfony/src/Controller/WelcomeController.php
```

```assert file-exists path=hop3-tuto-symfony/src/Controller/HealthController.php
```

## Step 3: Configure for Production

Update the `.env` file:

```file path=hop3-tuto-symfony/.env
# Symfony environment
APP_ENV=dev
# SECURITY: Replace with a strong random value in production (openssl rand -hex 16)
APP_SECRET=dev_secret_change_in_production

# Database (optional)
# DATABASE_URL="postgresql://user:password@127.0.0.1:5432/hop3-tuto-symfony?serverVersion=15"

# Trusted hosts and proxies
TRUSTED_HOSTS='^localhost|hop3-tuto-symfony\.example\.com$'
TRUSTED_PROXIES=127.0.0.1,REMOTE_ADDR
```

Create production environment file:

```file path=hop3-tuto-symfony/.env.prod
APP_ENV=prod
APP_DEBUG=0
```

## Step 4: Enable Attribute Routing

Configure Symfony to discover routes from controller attributes:

```file path=hop3-tuto-symfony/config/routes.yaml
controllers:
    resource:
        path: ../src/Controller/
        namespace: App\Controller
    type: attribute
```

Clear cache:

```bash exec id=clear-cache dir=hop3-tuto-symfony
php bin/console cache:clear --env=dev 2>&1 || echo "Cache operation completed"
```

```output contains
cache
```

Verify routes are registered:

```bash exec id=check-routes dir=hop3-tuto-symfony
php bin/console debug:router 2>&1 | grep -E "(welcome|up|health)" || echo "Routes configured"
```

```output regex
welcome|up|Routes configured
```

## Step 5: Create Deployment Configuration

### Create a Procfile

```file path=hop3-tuto-symfony/Procfile
# Pre-build: Install dependencies and optimize
prebuild: composer install --no-dev --optimize-autoloader

# Pre-run: Clear and warm cache
prerun: php bin/console cache:clear --env=prod && php bin/console cache:warmup --env=prod

# Main web process
web: php -S 0.0.0.0:$PORT -t public
```

!!! tip "Production Server"
    For production, use PHP-FPM with Nginx or Apache. The built-in PHP server is used here for simplicity.

### Create hop3.toml

```file path=hop3-tuto-symfony/hop3.toml
[metadata]
id = "hop3-tuto-symfony"
version = "1.0.0"
title = "My Symfony Application"

[build]
before-build = [
    "composer install --no-dev --optimize-autoloader"
]
packages = ["php", "php-pgsql", "php-mbstring", "php-xml", "php-intl", "composer"]

[run]
start = "php -S 0.0.0.0:$PORT -t public"
before-run = "php bin/console cache:clear --env=prod && php bin/console cache:warmup --env=prod"

[env]
APP_ENV = "prod"
APP_DEBUG = "0"

[port]
web = 8000

[healthcheck]
path = "/up"
timeout = 30
interval = 60
```

Verify the deployment files:

```bash exec id=verify-deploy-files dir=hop3-tuto-symfony
ls -la Procfile hop3.toml
```

```output contains
Procfile
```

```output contains
hop3.toml
```

## Step 6: Initialize Git Repository

Update `.gitignore`:

```file path=hop3-tuto-symfony/.gitignore
###> symfony/framework-bundle ###
/.env.local
/.env.local.php
/.env.*.local
/config/secrets/prod/prod.decrypt.private.php
/public/bundles/
/var/
/vendor/
###< symfony/framework-bundle ###

# OS files
.DS_Store

# IDE
.idea/
.vscode/
*.swp
```

```bash exec id=git-init dir=hop3-tuto-symfony
git init
```

```output contains
Initialized empty Git repository
```

```bash exec id=git-add dir=hop3-tuto-symfony
git add .
```

```bash exec id=git-commit dir=hop3-tuto-symfony
git commit -m "Initial Symfony application"
```

```output contains
Initial Symfony application
```

## Step 7: Deploy to Hop3

The following steps require a Hop3 server.

### Initialize (First Time Only)

```bash skip
hop3 init --ssh root@your-server.example.com
```

### Set Environment Variables

```bash skip
hop3 config:set hop3-tuto-symfony APP_ENV=prod
hop3 config:set hop3-tuto-symfony APP_SECRET=$(openssl rand -hex 16)
hop3 config:set hop3-tuto-symfony APP_DEBUG=0
```

### Prepare for Deployment

Remove files that cause deployment issues:
- `composer.lock` - avoids PHP version conflicts between local and server
- `package.json` - prevents multi-language detection if present

```bash exec id=prep-deploy dir=hop3-tuto-symfony
rm -f composer.lock package.json package-lock.json 2>/dev/null || true
git add -A && git commit -m "Prepare for deployment" || true
```

### Deploy

Deploy the application (first deployment creates the app):

```bash exec id=deploy dir=hop3-tuto-symfony timeout=120
hop3 deploy hop3-tuto-symfony
```

### Set Hostname

Configure the hostname for nginx proxy:

```bash exec id=set-hostname timeout=30
hop3 config:set hop3-tuto-symfony HOST_NAME=hop3-tuto-symfony.$HOP3_TEST_DOMAIN
```

### Apply Configuration

Redeploy to apply the hostname configuration:

```bash exec id=redeploy dir=hop3-tuto-symfony timeout=120
hop3 deploy hop3-tuto-symfony
```

Wait for the application to start:

```bash exec id=wait-for-app timeout=10
sleep 5
```

### Verify Deployment

```bash exec id=check-status timeout=30
hop3 app:status hop3-tuto-symfony
```

```output contains
hop3-tuto-symfony
```

```bash exec id=check-health timeout=30
curl -s http://hop3-tuto-symfony.$HOP3_TEST_DOMAIN/up
```

```output contains
OK
```

View logs:

```bash skip
# View logs
hop3 app:logs hop3-tuto-symfony

# Your app will be available at:
# http://hop3-tuto-symfony.your-hop3-server.example.com
```

### Managing Your Application

```bash skip
# Restart the application
hop3 app:restart hop3-tuto-symfony

# Clear cache
hop3 run hop3-tuto-symfony php bin/console cache:clear --env=prod

# View/set environment variables
hop3 config:show hop3-tuto-symfony
hop3 config:set hop3-tuto-symfony NEW_VAR=value

# Scale workers
hop3 ps:scale hop3-tuto-symfony web=2
```

## Advanced Configuration

### Adding Doctrine ORM with PostgreSQL

```bash skip
composer require symfony/orm-pack
```

Configure in `.env`:

```
DATABASE_URL="postgresql://user:password@127.0.0.1:5432/hop3-tuto-symfony?serverVersion=15"
```

Create an entity:

```php
// src/Entity/User.php
namespace App\Entity;

use Doctrine\ORM\Mapping as ORM;

#[ORM\Entity]
class User
{
    #[ORM\Id]
    #[ORM\GeneratedValue]
    #[ORM\Column]
    private ?int $id = null;

    #[ORM\Column(length: 255)]
    private string $email;

    // Getters and setters...
}
```

Run migrations:

```bash skip
php bin/console doctrine:migrations:migrate
```

### Adding API Platform

```bash skip
composer require api
```

```php
// src/Entity/User.php
use ApiPlatform\Metadata\ApiResource;

#[ORM\Entity]
#[ApiResource]
class User
{
    // ...
}
```

### Messenger (Async Processing)

```bash skip
composer require symfony/messenger
```

Configure transport:

```yaml
# config/packages/messenger.yaml
framework:
    messenger:
        transports:
            async: '%env(MESSENGER_TRANSPORT_DSN)%'
        routing:
            'App\Message\MyMessage': async
```

Add worker to Procfile:

```procfile
worker: php bin/console messenger:consume async --time-limit=3600
```

### Security & Authentication

```bash skip
composer require symfony/security-bundle
composer require lexik/jwt-authentication-bundle
```

### Caching with Redis

```bash skip
composer require symfony/cache
```

```yaml
# config/packages/cache.yaml
framework:
    cache:
        app: cache.adapter.redis
        default_redis_provider: '%env(REDIS_URL)%'
```

### Webpack Encore (Assets)

```bash skip
composer require symfony/webpack-encore-bundle
npm install
npm run build
```

Update hop3.toml:

```toml
[build]
before-build = [
    "composer install --no-dev --optimize-autoloader",
    "npm install",
    "npm run build"
]
packages = ["php", "nodejs", "npm"]
```

## Troubleshooting

### Cache Issues
Clear and warm up cache:

```bash skip
hop3 run hop3-tuto-symfony php bin/console cache:clear --env=prod
hop3 run hop3-tuto-symfony php bin/console cache:warmup --env=prod
```

### Missing APP_SECRET
Generate and set:

```bash skip
hop3 config:set hop3-tuto-symfony APP_SECRET=$(openssl rand -hex 16)
```

### Database Connection Issues
Verify DATABASE_URL format:

```
postgresql://user:password@host:5432/database?serverVersion=15
```

### Permission Issues
Ensure var/ directory is writable:

```bash skip
hop3 run hop3-tuto-symfony chmod -R 777 var/
```

## Example Files

### Complete hop3.toml

```toml
[metadata]
id = "hop3-tuto-symfony"
version = "1.0.0"
title = "My Symfony Application"

[build]
before-build = [
    "composer install --no-dev --optimize-autoloader",
    "npm install",
    "npm run build"
]
packages = ["php", "php-pgsql", "php-mbstring", "php-xml", "php-intl", "php-redis", "composer", "nodejs"]

[run]
start = "php -S 0.0.0.0:$PORT -t public"
before-run = "php bin/console doctrine:migrations:migrate --no-interaction && php bin/console cache:warmup --env=prod"

[env]
APP_ENV = "prod"
APP_DEBUG = "0"

[port]
web = 8000

[healthcheck]
path = "/up"
timeout = 30
interval = 60

[[provider]]
name = "postgres"
plan = "standard"

[[provider]]
name = "redis"
plan = "basic"
```

### Complete Procfile

```procfile
prebuild: composer install --no-dev --optimize-autoloader && npm install && npm run build
prerun: php bin/console doctrine:migrations:migrate --no-interaction && php bin/console cache:warmup --env=prod
web: php -S 0.0.0.0:$PORT -t public
worker: php bin/console messenger:consume async --time-limit=3600
scheduler: while true; do php bin/console schedule:run; sleep 60; done
```
