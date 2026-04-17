# Experience Report: Dolibarr

**Status:** Draft (0.5)
**App:** Dolibarr — ERP/CRM
**Language:** PHP
**Database:** PostgreSQL
**Website:** https://www.dolibarr.org/

## Deployment Methods

### Native (local builder)

- **Builder/Toolchain:** local/php
- **Addons:** PostgreSQL
- **Build steps:** composer install
- **Status:** Passing
- **Issues:** None

### Nix (hand-crafted hop3.nix)

- **Template equivalent:** php-app
- **Addons:** PostgreSQL
- **Status:** Passing
- **Issues:** None

### Nix (template-generated)

- **Template:** php-app
- **Key config:** web-root=htdocs, pgsql extensions
- **Addons:** PostgreSQL
- **Status:** Passing
- **Issues:** None

### Docker

- **Base image:** debian:trixie-slim
- **Addons:** PostgreSQL
- **Status:** Passing
- **Issues:** None

## Lessons Learned

- The web root differs from the Laravel/Symfony default: Dolibarr uses `htdocs` instead of `public`, requiring explicit web-root configuration.
- PostgreSQL is less common than MySQL for PHP apps, so this serves as a good test case for the PostgreSQL addon with PHP toolchains.
- Composer dependency resolution is straightforward for Dolibarr compared to other PHP apps.

## Cross-Method Comparison

All four deployment methods work without significant issues. The only notable configuration difference is the non-standard web root (`htdocs`), which must be specified in each method but is otherwise unremarkable.
