# Experience Report: Radicale

**Status:** Draft (0.5)
**App:** Radicale — CalDAV/CardDAV server
**Language:** Python
**Database:** None (file-based)
**Website:** https://radicale.org/

## Deployment Methods

### Native (local builder)

- **Builder/Toolchain:** local/python
- **Addons:** None
- **Build steps:** pip install
- **Status:** Passing
- **Issues:** None

### Nix (hand-crafted hop3.nix)

- **Template equivalent:** nixpkgs-wrapper
- **Addons:** None
- **Status:** Passing
- **Issues:** None

### Nix (template-generated)

- **Template:** nixpkgs-wrapper
- **Key config:** Uses nixpkgs package directly (no custom build)
- **Addons:** None
- **Status:** Passing
- **Issues:** None

### Docker

- **Base image:** debian:trixie-slim
- **Addons:** None (htpasswd auth configured)
- **Status:** Passing
- **Issues:** Docker uses htpasswd authentication while other methods use no auth.

## Lessons Learned

- The nixpkgs-wrapper template is ideal for apps already packaged in nixpkgs, avoiding any custom build logic.
- File-based storage means no addon complexity, making this the simplest app to deploy across all methods.
- Simplest Python app to package: pip install plus a config file is all that is needed.

## Cross-Method Comparison

All methods pass without issues. Radicale's zero-addon, file-based design makes it the lowest-friction app in the set. The only difference across methods is auth configuration (htpasswd in Docker vs none elsewhere).
