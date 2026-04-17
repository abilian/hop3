# Experience Report: Isso

**Status:** Draft (0.5)
**App:** Isso — Commenting system
**Language:** Python
**Database:** None (SQLite)
**Website:** https://isso-comments.de/

## Deployment Methods

### Native (local builder)

- **Builder/Toolchain:** local/python
- **Addons:** None
- **Build steps:** pip install
- **Status:** Passing
- **Issues:** None

### Nix (hand-crafted hop3.nix)

- **Template equivalent:** python-venv
- **Addons:** None
- **Status:** Passing
- **Issues:** None

### Nix (template-generated)

- **Template:** python-venv
- **Key config:** isso + gunicorn packages, config.cfg generation
- **Addons:** None
- **Status:** Passing
- **Issues:** None

### Docker

- **Base image:** debian:trixie-slim
- **Addons:** None
- **Status:** Passing (expects HTTP 400)
- **Issues:** Isso returns HTTP 400 by design when no Origin header is present, which complicates generic health-check testing. The test validation expects 400 instead of 200.

## Lessons Learned

- The Python venv template works cleanly for Isso with no special workarounds needed.
- Isso requires a specific Origin HTTP header on all requests, which means generic HTTP health checks return 400. Test validations must account for this.
- SQLite-based apps are the simplest to deploy since they eliminate all database provisioning and connection configuration.
- Running isso behind gunicorn is the standard production pattern and maps naturally to the python-venv template.

## Cross-Method Comparison

All methods work well for Isso given its simplicity (Python + SQLite). The only quirk is the HTTP 400 response without an Origin header, which affects testing validation across all methods equally rather than being specific to any one deployment approach.
