# Experience Report: LimeSurvey

**Status:** Draft (0.5)
**App:** LimeSurvey — Survey platform
**Language:** PHP
**Database:** PostgreSQL
**Website:** https://www.limesurvey.org/

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
- **Key config:** PostgreSQL extensions, console install command, config.php generation
- **Addons:** PostgreSQL
- **Status:** Passing
- **Issues:** None

### Docker

- **Base image:** debian:trixie-slim
- **Addons:** PostgreSQL
- **Status:** Passing
- **Issues:** None

## Lessons Learned

- Config files must be generated BEFORE pre-exec commands: the console install command needs config.php to know the DB connection details.
- Uses PostgreSQL unlike most PHP apps in the set, which default to MySQL.
- The console install command auto-creates all required database tables, avoiding manual migration steps.

## Cross-Method Comparison

All methods pass once the config generation ordering is correct. The key insight is that config.php must exist before the install command runs, which applies equally to native and Nix deployments.
