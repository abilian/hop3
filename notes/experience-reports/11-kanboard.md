# Experience Report: Kanboard

**Status:** Draft (0.5)
**App:** Kanboard — Kanban board
**Language:** PHP
**Database:** MySQL
**Website:** https://kanboard.org/

## Deployment Methods

### Native (local builder)

- **Builder/Toolchain:** local/php
- **Addons:** MySQL
- **Build steps:** No composer needed; PHP files served directly
- **Status:** Passing
- **Issues:** None

### Nix (hand-crafted hop3.nix)

- **Template equivalent:** php-app
- **Addons:** MySQL
- **Status:** Passing
- **Issues:** None

### Nix (template-generated)

- **Template:** php-app
- **Key config:** includes pdo_sqlite extension
- **Addons:** MySQL
- **Status:** Passing
- **Issues:** None

### Docker

- **Base image:** debian:trixie-slim
- **Addons:** MySQL
- **Status:** Passing
- **Issues:** None

## Lessons Learned

- Simplest PHP app to package: no composer, no build step required.
- Works with both MySQL and SQLite as the backing database.
- Permissions (chmod) matter for the data directory; the app writes session and task data there.

## Cross-Method Comparison

All four deployment methods work without friction. Kanboard's zero-build-step nature makes it an ideal baseline for testing PHP deployment pipelines.
