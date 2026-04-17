# Experience Report: WordPress

**Status:** Draft (0.5)
**App:** WordPress — CMS
**Language:** PHP
**Database:** MySQL
**Website:** https://wordpress.org/

## Deployment Methods

### Native (local builder)

- **Builder/Toolchain:** local/php
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
- **Key config:** Extensive extensions, post-install directories (uploads/plugins/themes)
- **Addons:** MySQL
- **Status:** Passing
- **Issues:** None

### Docker

- **Base image:** debian:trixie-slim
- **Addons:** MySQL
- **Status:** Was 500 (fixed)
- **Issues:** Missing MySQL wait loop caused Apache to start before MySQL was ready, resulting in 500 errors. Fixed by adding a wait loop.

## Lessons Learned

- Simplest PHP CMS to package: no composer, no build step required.
- wp-config.php reads environment variables via getenv(), so config generation only needs to set up the env var bridge.
- Docker must wait for MySQL before starting Apache; the missing wait loop was the sole cause of the 500 error.
- The WordPress install wizard returns HTTP 200, so no special handling is needed for fresh-install health checks.

## Cross-Method Comparison

Native and Nix deployments pass without issues. Docker required a MySQL wait loop fix, reinforcing the lesson from Matomo that container startup ordering must be explicitly managed. WordPress's use of getenv() in wp-config.php makes it unusually clean to configure across all methods.
