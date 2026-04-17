# Experience Report: Easy!Appointments

**Status:** Draft (0.5)
**App:** Easy!Appointments — Online scheduling
**Language:** PHP/CodeIgniter
**Database:** MySQL
**Website:** https://easyappointments.org/

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
- **Key config:** needs composer
- **Addons:** MySQL
- **Status:** Passing
- **Issues:** None

### Docker

- **Base image:** debian:trixie-slim
- **Addons:** MySQL
- **Status:** Passing (was failing)
- **Issues:** Previously returned HTTP 500 due to MySQL race condition. Fixed by adding MySQL wait loop and auto DB schema creation.

## Lessons Learned

- CodeIgniter lacks an artisan-style CLI for running migrations, so database schema creation must be handled through other means (direct SQL or auto-install endpoints).
- Docker deployments need explicit DB schema auto-creation since there is no migration CLI to call at startup.
- The app returns HTTP 200 only after the initial data seed has been applied, which complicates health-check validation.
- MySQL race conditions in Docker are a recurring theme across PHP apps and always require a wait loop.

## Cross-Method Comparison

Native and Nix deployments work cleanly once composer dependencies are installed. Docker required extra work to handle MySQL startup ordering and automatic schema creation, making it the most complex method for this app despite the app itself being relatively simple.
