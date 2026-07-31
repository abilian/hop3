---
app: wordpress
title: WordPress
version: "6.4.2"
upstream: https://wordpress.org/
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
  nix-gen: {status: pass, template: php-app}
---

# Experience Report: WordPress

Popular open source content management system. Packaged for Hop3 across the native, Docker and Nix build paths, and published in the signed catalog.

## What this app exercised

Not yet written. The earlier report recorded deployment status only, and did not say which edge of the platform this application was chosen to probe.

## What broke

- Simplest PHP CMS to package: no composer, no build step required.
- wp-config.php reads environment variables via getenv(), so config generation only needs to set up the env var bridge.
- Docker must wait for MySQL before starting Apache; the missing wait loop was the sole cause of the 500 error.
- The WordPress install wizard returns HTTP 200, so no special handling is needed for fresh-install health checks.

## What the platform gained

Not yet written — the earlier report did not record whether this application forced a change to Hop3 or merely confirmed one.

## Cost

Not recorded. The earlier reports did not track effort, and it cannot be reconstructed after the fact.

## Deployment variants

### Native

- **Builder/Toolchain:** local/php
- **Addons:** MySQL
- **Build steps:** No build step; PHP files served directly

### Docker

- **Base image:** debian:trixie-slim
- **Addons:** MySQL

### Nix (hand-crafted)

No recipe for this variant.

### Nix (template-generated)

- **Template:** `php-app`
- **Key config:** Extensive extensions, post-install directories (uploads/plugins/themes)
- **Addons:** MySQL

## Verification

`apps/wordpress/check.py` runs against the deployed application and asserts, in order:

1. the probe-or-admin credential signs in
1. a wrong password is refused

It signs in with the credential Hop3 generated — the `[probe]` account where the recipe declares one, otherwise the `[admin]` credential, which is the weaker claim because the operator owns it.

## Reproduce

```bash
hop3 catalog install wordpress
hop3 app check --app wordpress
```

## Open

- **docker (not-attempted):** a recipe exists, but no run has measured it at the sign-in bar.
- The earlier report's cross-method comparison is retained below but predates every status above:

  > Native and Nix deployments pass without issues. Docker required a MySQL wait loop fix, reinforcing the lesson from Matomo that container startup ordering must be explicitly managed. WordPress's use of getenv() in wp-config.php makes it unusually clean to configure across all methods.

## Screenshots

![Sign-in page](images/wordpress-01-login.png)
![After signing in](images/wordpress-02-signed-in.png)
