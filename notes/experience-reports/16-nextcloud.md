# Experience Report: NextCloud

**Status:** Draft (0.5)
**App:** NextCloud — File sync and collaboration
**Language:** PHP
**Database:** MySQL (native/nix) or PostgreSQL+Redis (docker)
**Website:** https://nextcloud.com/

## Deployment Methods

### Native (local builder)

- **Builder/Toolchain:** local/generic
- **Addons:** MySQL
- **Build steps:** No build step; PHP files served directly
- **Status:** Passing
- **Issues:** None

### Nix (hand-crafted hop3.nix)

- **Template equivalent:** php-app
- **Addons:** MySQL
- **Status:** Passing
- **Issues:** None

### Nix (template-generated)

- **Template:** php-app
- **Key config:** Extensive extensions (apcu, opcache), autoconfig.php generation
- **Addons:** MySQL
- **Status:** Passing
- **Issues:** None

### Docker

- **Base image:** debian:trixie-slim
- **Addons:** PostgreSQL, Redis
- **Status:** Partial
- **Issues:** Docker config uses a different addon set (PostgreSQL+Redis instead of MySQL). Partially working.

## Lessons Learned

- Most complex PHP app to package due to many required extensions, cron jobs, and background task configuration.
- Docker deployment uses a different database (PostgreSQL) and adds Redis, showing how deployment methods can diverge in addon requirements.
- autoconfig.php handles first-run setup automatically, avoiding the need for manual installation through the web UI.
- Extension requirements (apcu, opcache) must be explicitly declared in the Nix config.

## Cross-Method Comparison

Native and Nix deployments pass with MySQL. Docker uses a different addon configuration (PostgreSQL+Redis), which makes it not directly comparable and is only partially working. NextCloud is the most complex PHP app in the set and stress-tests the php-app template's extension and config generation capabilities.
