---
app: nextcloud
title: Nextcloud
version: "28.0.2"
upstream: https://nextcloud.com/
languages: [php]
databases: [mysql]
in_catalog: true
report_status: draft
last_verified: 2026-07-31
verified_bar: authenticated

variants:
  native: {status: pass}
  docker: {status: not-attempted}
  nix: {status: no-recipe, reason: "superseded in practice by the template variant; no recipe here"}
  nix-gen: {status: fail}
---

# Experience Report: Nextcloud

Self-hosted productivity platform. Packaged for Hop3 across the native, Docker and Nix build paths, and published in the signed catalog.

## What this app exercised

Not yet written. The earlier report recorded deployment status only, and did not say which edge of the platform this application was chosen to probe.

## What broke

- Most complex PHP app to package due to many required extensions, cron jobs, and background task configuration.
- Docker deployment uses a different database (PostgreSQL) and adds Redis, showing how deployment methods can diverge in addon requirements.
- autoconfig.php handles first-run setup automatically, avoiding the need for manual installation through the web UI.
- Extension requirements (apcu, opcache) must be explicitly declared in the Nix config.

## What the platform gained

Not yet written — the earlier report did not record whether this application forced a change to Hop3 or merely confirmed one.

## Cost

Not recorded. The earlier reports did not track effort, and it cannot be reconstructed after the fact.

## Deployment variants

### Native

- **Builder/Toolchain:** local/generic
- **Addons:** MySQL
- **Build steps:** No build step; PHP files served directly

### Docker

- **Base image:** debian:trixie-slim
- **Addons:** PostgreSQL, Redis

### Nix (hand-crafted)

No recipe for this variant.

### Nix (template-generated)

- **Template:** `php-app`
- **Key config:** Extensive extensions (apcu, opcache), autoconfig.php generation
- **Addons:** MySQL

## Verification

`apps/nextcloud/check.py` runs against the deployed application and asserts, in order:

1. the probe-or-admin credential signs in
1. a wrong password is refused

It signs in with the credential Hop3 generated — the `[probe]` account where the recipe declares one, otherwise the `[admin]` credential, which is the weaker claim because the operator owns it.

## Reproduce

```bash
hop3 catalog install nextcloud
hop3 app check --app nextcloud
```

## Open

- **nix-gen (fail):** `GET /login` answers 400; the app is not installed.
- **docker (not-attempted):** a recipe exists, but no run has measured it at the sign-in bar.
- The earlier report's cross-method comparison is retained below but predates every status above:

  > Native and Nix deployments pass with MySQL. Docker uses a different addon configuration (PostgreSQL+Redis), which makes it not directly comparable and is only partially working. NextCloud is the most complex PHP app in the set and stress-tests the php-app template's extension and config generation capabilities.

## Screenshots

![Sign-in page](images/nextcloud-01-login.png)
![After signing in](images/nextcloud-02-signed-in.png)
