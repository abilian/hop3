---
app: mattermost
title: Mattermost
version: "9.4.2"
upstream: https://mattermost.com/
languages: [go]
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

# Experience Report: Mattermost

Open source team collaboration platform. Packaged for Hop3 across the native, Docker and Nix build paths, and published in the signed catalog.

## What this app exercised

Not yet written. The earlier report recorded deployment status only, and did not say which edge of the platform this application was chosen to probe.

## What broke

- Pre-built Go archive includes both the binary and an asset directory (templates, i18n, static files).
- Needs symlinks from the writable data directory back to the Nix store for static assets, since Mattermost expects assets relative to its binary.
- JSON config generation from environment variables works well and avoids maintaining a separate config template.
- The pre-exec step for symlinking is more complex than most apps but follows a repeatable pattern.

## What the platform gained

Not yet written — the earlier report did not record whether this application forced a change to Hop3 or merely confirmed one.

## Cost

Not recorded. The earlier reports did not track effort, and it cannot be reconstructed after the fact.

## Deployment variants

### Native

- **Builder/Toolchain:** local/generic
- **Addons:** PostgreSQL
- **Build steps:** Pre-built binary extracted from archive

### Docker

- **Base image:** debian:trixie-slim
- **Addons:** PostgreSQL

### Nix (hand-crafted)

- **Template equivalent:** prebuilt-archive
- **Addons:** PostgreSQL

### Nix (template-generated)

- **Template:** `nixpkgs-wrapper`
- **Key config:** Complex pre-exec (asset symlinking), config.json generation from environment variables
- **Addons:** PostgreSQL

## Verification

`apps/mattermost/check.py` runs against the deployed application and asserts, in order:

1. the probe-or-admin credential signs in
1. a wrong password is refused

It signs in with the credential Hop3 generated — the `[probe]` account where the recipe declares one, otherwise the `[admin]` credential, which is the weaker claim because the operator owns it.

## Reproduce

```bash
hop3 catalog install mattermost
hop3 app check --app mattermost
```

## Open

- **nix-gen (fail):** the deploy itself fails; not yet diagnosed.
- **docker (not-attempted):** a recipe exists, but no run has measured it at the sign-in bar.
- **nix (not-attempted):** the hand-crafted recipe exists and has not been run at the sign-in bar.
- The earlier report's cross-method comparison is retained below but predates every status above:

  > All deployment methods pass. The main complexity is asset directory management, which the prebuilt-archive template handles via symlinking. Native and Docker deployments avoid this since assets live alongside the binary in a writable filesystem. The pre-built archive approach limits deployment to x86_64-linux; ARM and other architectures are not currently supported.

## Screenshots

![Sign-in page](images/mattermost-01-login.png)
![After signing in](images/mattermost-02-signed-in.png)
