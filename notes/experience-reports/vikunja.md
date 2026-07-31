---
app: vikunja
title: Vikunja
version: "0.x"
upstream: https://vikunja.io/
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

# Experience Report: Vikunja

Open source task and project management. Packaged for Hop3 across the native, Docker and Nix build paths, and published in the signed catalog.

## What this app exercised

Not yet written. The earlier report recorded deployment status only, and did not say which edge of the platform this application was chosen to probe.

## What broke

- YAML config generation works well for Go apps that expect a config.yml file.
- ZIP archive extraction is supported alongside tar.gz, broadening the prebuilt-archive template's applicability.
- Follows a consistent pre-built binary pattern shared with Mattermost and Miniflux, confirming that Go apps are straightforward to package.

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

- **Template:** `go-source`
- **Key config:** ZIP archive extraction, config.yml generation
- **Addons:** PostgreSQL

## Verification

`apps/vikunja/check.py` runs against the deployed application and asserts, in order:

1. the probe-or-admin credential signs in
1. the token opens an authenticated route
1. a wrong password is refused

It signs in with the credential Hop3 generated — the `[probe]` account where the recipe declares one, otherwise the `[admin]` credential, which is the weaker claim because the operator owns it.

## Reproduce

```bash
hop3 catalog install vikunja
hop3 app check --app vikunja
```

## Open

- **nix-gen (fail):** the frontend derivation does not build.
- **docker (not-attempted):** a recipe exists, but no run has measured it at the sign-in bar.
- **nix (not-attempted):** the hand-crafted recipe exists and has not been run at the sign-in bar.
- The earlier report's cross-method comparison is retained below but predates every status above:

  > All deployment methods pass cleanly. Vikunja follows the same pre-built Go binary pattern as other Go apps in the set, with YAML config generation being the only notable difference from the JSON-based Mattermost config. The pre-built binary approach limits deployment to x86_64-linux; ARM and other architectures are not currently supported.

## Screenshots

![Sign-in page](images/vikunja-01-login.png)
![After signing in](images/vikunja-02-signed-in.png)
