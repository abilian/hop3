# Experience Report: Matomo

**Status:** Draft (0.5)
**App:** Matomo — Web analytics
**Language:** PHP
**Database:** MySQL
**Website:** https://matomo.org/

## Deployment Methods

### Native (local builder)

- **Builder/Toolchain:** local/php
- **Addons:** MySQL
- **Build steps:** No build step required
- **Status:** Passing
- **Issues:** None

### Nix (hand-crafted hop3.nix)

- **Template equivalent:** php-app
- **Addons:** MySQL
- **Status:** Passing
- **Issues:** None

### Nix (template-generated)

- **Template:** php-app
- **Key config:** needs-writable-dir, config.ini.php generation
- **Addons:** MySQL
- **Status:** Passing
- **Issues:** None

### Docker

- **Base image:** debian:trixie-slim
- **Addons:** MySQL
- **Status:** Was 500 (fixed)
- **Issues:** Fresh install tried to query missing tables. Fixed by adding installation_in_progress flag to config.ini.php and adding a MySQL wait loop.

## Lessons Learned

- PHP apps that detect installation state need special handling during first deployment.
- Matomo crashes with a 500 error if config.ini.php exists but the database tables have not been created yet.
- Setting the `installation_in_progress` INI flag causes Matomo to show the installer wizard instead of crashing, which returns a 200 status.
- Docker required a MySQL wait loop to ensure the database was ready before the app started.

## Cross-Method Comparison

Native and Nix deployments pass cleanly. Docker required two fixes (MySQL wait loop and installation_in_progress flag) to avoid the 500 error on fresh installs, highlighting how container startup ordering creates issues that don't appear in traditional deployments.
