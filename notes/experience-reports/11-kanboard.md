---
app: kanboard
title: Kanboard
version: "1.2.37"
upstream: https://kanboard.org/
languages: [php]
databases: [mysql]
in_catalog: true
report_status: draft
last_verified: 2026-07-31
verified_bar: authenticated

variants:
  native: {status: pass}
  docker: {status: not-attempted}
  nix: {status: not-attempted}
  nix-gen: {status: fail}
---

# Experience Report: Kanboard

Kanban project management software. Packaged for Hop3 across the native, Docker and Nix build paths, and published in the signed catalog.

## What this app exercised

Not yet written. The earlier report recorded deployment status only, and did not say which edge of the platform this application was chosen to probe.

## What broke

- Simplest PHP app to package: no composer, no build step required.
- Works with both MySQL and SQLite as the backing database.
- Permissions (chmod) matter for the data directory; the app writes session and task data there.

## What the platform gained

Not yet written — the earlier report did not record whether this application forced a change to Hop3 or merely confirmed one.

## Cost

Not recorded. The earlier reports did not track effort, and it cannot be reconstructed after the fact.

## Deployment variants

### Native

- **Builder/Toolchain:** local/php
- **Addons:** MySQL
- **Build steps:** No composer needed; PHP files served directly

### Docker

- **Base image:** debian:trixie-slim
- **Addons:** MySQL

### Nix (hand-crafted)

- **Template equivalent:** php-app
- **Addons:** MySQL

### Nix (template-generated)

- **Template:** `php-app`
- **Key config:** includes pdo_sqlite extension
- **Addons:** MySQL

## Verification

`apps/kanboard/check.py` runs against the deployed application and asserts, in order:

1. the probe-or-admin credential signs in
1. a wrong password is refused

It signs in with the credential Hop3 generated — the `[probe]` account where the recipe declares one, otherwise the `[admin]` credential, which is the weaker claim because the operator owns it.

## Reproduce

```bash
hop3 catalog install kanboard
hop3 app check --app kanboard
```

## Open

- **nix-gen (fail):** the app deploys but has no admin account; its native bootstrap has not been ported.
- **docker (not-attempted):** a recipe exists, but no run has measured it at the sign-in bar.
- **nix (not-attempted):** the hand-crafted recipe exists and has not been run at the sign-in bar.
- The earlier report's cross-method comparison is retained below but predates every status above:

  > All four deployment methods work without friction. Kanboard's zero-build-step nature makes it an ideal baseline for testing PHP deployment pipelines.

## Screenshots

![Sign-in page](images/kanboard-01-login.png)
![After signing in](images/kanboard-02-signed-in.png)
