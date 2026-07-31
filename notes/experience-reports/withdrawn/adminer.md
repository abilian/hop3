---
app: adminer
title: Adminer
version: "4.8.1"
upstream: https://www.adminer.org/
languages: [php]
databases: []
in_catalog: false
report_status: withdrawn
last_verified: 2026-04-09
verified_bar: http-status

variants:
  native: {status: not-attempted}
  docker: {status: no-recipe, reason: "dropped from the corpus with the application"}
  nix: {status: not-attempted}
  nix-gen: {status: not-attempted}
---
# Experience Report: Adminer

> **Withdrawn.** Adminer is no longer part of the packaged corpus and is not published in the catalog, so nothing here is maintained or re-verified. It is kept because the packaging work was real and the findings below may still save someone time. Everything it says was measured at the *deployed and serving* bar — not by signing in — which is the bar the current reports reject.

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
