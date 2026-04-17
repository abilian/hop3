# Experience Report: Adminer

**Status:** Draft (0.5)
**App:** Adminer — Lightweight database admin tool
**Language:** PHP
**Database:** None
**Website:** https://www.adminer.org/

## Deployment Methods

### Native (local builder)

- **Builder/Toolchain:** local/php
- **Addons:** None
- **Build steps:** No build step needed (single-file PHP app)
- **Status:** Passing
- **Issues:** None

### Nix (hand-crafted hop3.nix)

- **Template equivalent:** php-app
- **Addons:** None
- **Status:** Passing
- **Issues:** None

### Nix (template-generated)

- **Template:** php-app
- **Key config:** php82 with mysqli, pgsql, and pdo extensions
- **Addons:** None
- **Status:** Passing
- **Issues:** None

### Docker

- **Base image:** N/A
- **Addons:** N/A
- **Status:** Untested
- **Issues:** No Docker version exists

## Lessons Learned

- Single-file PHP app makes this the simplest possible package to deploy.
- No build step is needed at all, making it an ideal first test case.
- Demonstrates PHP extension management in Nix (mysqli, pgsql, pdo) even though the app itself is trivial.

## Cross-Method Comparison

Adminer is so simple that native and Nix deployments are nearly identical in complexity. The main value of the Nix path is exercising PHP extension configuration, which matters more for larger apps.
