---
app: dolibarr
title: Dolibarr
version: "19.0"
upstream: https://www.dolibarr.org/
languages: [php]
databases: [postgres]
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

# Experience Report: Dolibarr

Open source ERP and CRM for small and medium businesses. Packaged for Hop3 across the native, Docker and Nix build paths, and published in the signed catalog.

## What this app exercised

Not yet written. The earlier report recorded deployment status only, and did not say which edge of the platform this application was chosen to probe.

## What broke

- The web root differs from the Laravel/Symfony default: Dolibarr uses `htdocs` instead of `public`, requiring explicit web-root configuration.
- PostgreSQL is less common than MySQL for PHP apps, so this serves as a good test case for the PostgreSQL addon with PHP toolchains.
- Composer dependency resolution is straightforward for Dolibarr compared to other PHP apps.

## What the platform gained

Not yet written — the earlier report did not record whether this application forced a change to Hop3 or merely confirmed one.

## Cost

Not recorded. The earlier reports did not track effort, and it cannot be reconstructed after the fact.

## Deployment variants

### Native

- **Builder/Toolchain:** local/php
- **Addons:** PostgreSQL
- **Build steps:** composer install

### Docker

- **Base image:** debian:trixie-slim
- **Addons:** PostgreSQL

### Nix (hand-crafted)

- **Template equivalent:** php-app
- **Addons:** PostgreSQL

### Nix (template-generated)

- **Template:** `php-app`
- **Key config:** web-root=htdocs, pgsql extensions
- **Addons:** PostgreSQL

## Verification

`apps/dolibarr/check.py` runs against the deployed application and asserts, in order:

1. the probe-or-admin credential signs in
1. a wrong password is refused

It signs in with the credential Hop3 generated — the `[probe]` account where the recipe declares one, otherwise the `[admin]` credential, which is the weaker claim because the operator owns it.

## Reproduce

```bash
hop3 catalog install dolibarr
hop3 app check --app dolibarr
```

## Open

- **nix-gen (fail):** the app deploys but is never installed; its native bootstrap has not been ported (`before-run` was unusable for Nix apps until 2026-07-31).
- **docker (not-attempted):** a recipe exists, but no run has measured it at the sign-in bar.
- **nix (not-attempted):** the hand-crafted recipe exists and has not been run at the sign-in bar.
- The earlier report's cross-method comparison is retained below but predates every status above:

  > All four deployment methods work without significant issues. The only notable configuration difference is the non-standard web root (`htdocs`), which must be specified in each method but is otherwise unremarkable.

## Screenshots

![Sign-in page](images/dolibarr-01-login.png)
![After signing in](images/dolibarr-02-signed-in.png)
