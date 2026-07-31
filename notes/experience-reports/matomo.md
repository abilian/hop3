---
app: matomo
title: Matomo
version: "5.0.1"
upstream: https://matomo.org/
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

# Experience Report: Matomo

Open source web analytics platform. Packaged for Hop3 across the native, Docker and Nix build paths, and published in the signed catalog.

## What this app exercised

An application with no user-creation CLI at all — its installer is a browser wizard — so the account is made by driving Matomo's own model classes from PHP.

## What broke

- PHP apps that detect installation state need special handling during first deployment.
- Matomo crashes with a 500 error if config.ini.php exists but the database tables have not been created yet.
- Setting the `installation_in_progress` INI flag causes Matomo to show the installer wizard instead of crashing, which returns a 200 status.
- Docker required a MySQL wait loop to ensure the database was ready before the app started.

## What the platform gained

`[probe].create` is now required rather than optional: a probe account Hop3 cannot create is one it can never offer to a check, and the optional form silently did nothing.

## Cost

Not recorded. The earlier reports did not track effort, and it cannot be reconstructed after the fact.

## Deployment variants

### Native

- **Builder/Toolchain:** local/php
- **Addons:** MySQL
- **Build steps:** No build step required

### Docker

- **Base image:** debian:trixie-slim
- **Addons:** MySQL

### Nix (hand-crafted)

- **Template equivalent:** php-app
- **Addons:** MySQL

### Nix (template-generated)

- **Template:** `php-app`
- **Key config:** needs-writable-dir, config.ini.php generation
- **Addons:** MySQL

## Verification

`apps/matomo/check.py` runs against the deployed application and asserts, in order:

1. the probe-or-admin credential signs in
1. a wrong password is refused

It signs in with the credential Hop3 generated — the `[probe]` account where the recipe declares one, otherwise the `[admin]` credential, which is the weaker claim because the operator owns it.

## Reproduce

```bash
hop3 catalog install matomo
hop3 app check --app matomo
```

## Open

- **nix-gen (fail):** the bootstrap is ported but blocked: `needs-writable-dir` materialises the app tree when the app starts, which is after `before-run`, so the installer found no application to install.
- **docker (not-attempted):** a recipe exists, but no run has measured it at the sign-in bar.
- **nix (not-attempted):** the hand-crafted recipe exists and has not been run at the sign-in bar.
- The earlier report's cross-method comparison is retained below but predates every status above:

  > Native and Nix deployments pass cleanly. Docker required two fixes (MySQL wait loop and installation_in_progress flag) to avoid the 500 error on fresh installs, highlighting how container startup ordering creates issues that don't appear in traditional deployments.

## Screenshots

![Sign-in page](images/matomo-01-login.png)
![After signing in](images/matomo-02-signed-in.png)
