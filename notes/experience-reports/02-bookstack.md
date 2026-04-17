# Experience Report: BookStack

**Status:** Draft (0.5)
**App:** BookStack — Self-hosted wiki platform
**Language:** PHP/Laravel
**Database:** MySQL
**Website:** https://www.bookstackapp.com/

## Deployment Methods

### Native (local builder)

- **Builder/Toolchain:** local/php
- **Addons:** MySQL
- **Build steps:** composer install
- **Status:** Passing
- **Issues:** None

### Nix (hand-crafted hop3.nix)

- **Template equivalent:** php-app
- **Addons:** MySQL
- **Status:** Passing
- **Issues:** None

### Nix (template-generated)

- **Template:** php-app
- **Key config:** needs-writable-dir, APP_KEY generation
- **Addons:** MySQL
- **Status:** Passing
- **Issues:** None

### Docker

- **Base image:** debian:trixie-slim
- **Addons:** MySQL
- **Status:** Passing (was failing)
- **Issues:** Previously returned HTTP 500 due to APP_KEY/migration issues. Fixed by adding MySQL wait loop, making migrations non-fatal, and fixing APP_KEY newline corruption.

## Lessons Learned

- Laravel APP_KEY must be exactly 32 bytes base64-encoded; trailing newlines or truncation cause cryptic 500 errors.
- PHP's `__DIR__` resolves symlinks, which breaks Nix store paths. The workaround is using `cp -a` instead of symlinks.
- Database migrations must be non-fatal in Docker to handle race conditions where the app starts before MySQL is ready.
- MySQL wait loops are essential in Docker Compose setups to avoid startup ordering failures.

## Cross-Method Comparison

Native and Nix deployments are straightforward once the APP_KEY and symlink issues are understood. Docker required the most debugging due to MySQL startup races and APP_KEY newline corruption, making it the least reliable method initially but now on par with the others after fixes.
