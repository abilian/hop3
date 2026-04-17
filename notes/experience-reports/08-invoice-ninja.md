# Experience Report: Invoice Ninja

**Status:** Draft (0.5)
**App:** Invoice Ninja — Invoicing/finance
**Language:** PHP/Laravel
**Database:** MySQL
**Website:** https://invoiceninja.com/

## Deployment Methods

### Native (local builder)

- **Builder/Toolchain:** local/php
- **Addons:** MySQL
- **Build steps:** composer install + npm build for frontend assets
- **Status:** Passing
- **Issues:** None

### Nix (hand-crafted hop3.nix)

- **Template equivalent:** php-app
- **Addons:** MySQL
- **Status:** Passing
- **Issues:** None

### Nix (template-generated)

- **Template:** php-app
- **Key config:** nodejs dependency, artisan migrations, .env generation
- **Addons:** MySQL
- **Status:** Passing
- **Issues:** None

### Docker

- **Base image:** debian:trixie-slim
- **Addons:** MySQL
- **Status:** Passing (was failing)
- **Issues:** Previously timed out because `set -e` killed the container when migrations failed. Fixed by adding MySQL wait loop, making migrations non-fatal, fixing APP_KEY newline corruption, and using `--ignore-platform-reqs` for composer.

## Lessons Learned

- Laravel apps need careful APP_KEY handling: the key must be exactly 32 bytes base64-encoded, and newline corruption is a recurring issue across deployment methods.
- The `composer --ignore-platform-reqs` flag is needed when the installed PHP version does not exactly match the version specified in composer.json, which is common in containerized environments.
- npm asset compilation adds a second toolchain dependency (Node.js), increasing build complexity similar to Go/Node hybrid apps.
- Docker failures caused by `set -e` killing the entrypoint on non-fatal migration errors are subtle and hard to diagnose without logs.

## Cross-Method Comparison

Native and Nix are comparable once dependencies are resolved, though both require managing PHP and Node toolchains. Docker was the most problematic method due to compounding issues (MySQL races, APP_KEY corruption, strict error handling, PHP version mismatches), but is now stable after targeted fixes.
