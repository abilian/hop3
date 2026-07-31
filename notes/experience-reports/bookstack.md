---
app: bookstack
title: BookStack
version: "24.02"
upstream: https://www.bookstackapp.com/
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
  nix-gen: {status: pass, template: php-app}
---

# Experience Report: BookStack

Simple, self-hosted documentation platform. Packaged for Hop3 across the native, Docker and Nix build paths, and published in the signed catalog.

## What this app exercised

Not yet written. The earlier report recorded deployment status only, and did not say which edge of the platform this application was chosen to probe.

## What broke

- Laravel APP_KEY must be exactly 32 bytes base64-encoded; trailing newlines or truncation cause cryptic 500 errors.
- PHP's `__DIR__` resolves symlinks, which breaks Nix store paths. The workaround is using `cp -a` instead of symlinks.
- Database migrations must be non-fatal in Docker to handle race conditions where the app starts before MySQL is ready.
- MySQL wait loops are essential in Docker Compose setups to avoid startup ordering failures.

## What the platform gained

Not yet written — the earlier report did not record whether this application forced a change to Hop3 or merely confirmed one.

## Cost

Not recorded. The earlier reports did not track effort, and it cannot be reconstructed after the fact.

## Deployment variants

### Native

- **Builder/Toolchain:** local/php
- **Addons:** MySQL
- **Build steps:** composer install

### Docker

- **Base image:** debian:trixie-slim
- **Addons:** MySQL

### Nix (hand-crafted)

- **Template equivalent:** php-app
- **Addons:** MySQL

### Nix (template-generated)

- **Template:** `php-app`
- **Key config:** needs-writable-dir, APP_KEY generation
- **Addons:** MySQL

## Verification

`apps/bookstack/check.py` runs against the deployed application and asserts, in order:

1. the probe-or-admin credential signs in
1. a wrong password is refused

It signs in with the credential Hop3 generated — the `[probe]` account where the recipe declares one, otherwise the `[admin]` credential, which is the weaker claim because the operator owns it.

## Reproduce

```bash
hop3 catalog install bookstack
hop3 app check --app bookstack
```

## Open

- **docker (not-attempted):** a recipe exists, but no run has measured it at the sign-in bar.
- **nix (not-attempted):** the hand-crafted recipe exists and has not been run at the sign-in bar.
- The earlier report's cross-method comparison is retained below but predates every status above:

  > Native and Nix deployments are straightforward once the APP_KEY and symlink issues are understood. Docker required the most debugging due to MySQL startup races and APP_KEY newline corruption, making it the least reliable method initially but now on par with the others after fixes.

## Screenshots

![Sign-in page](images/bookstack-01-login.png)
![After signing in](images/bookstack-02-signed-in.png)
