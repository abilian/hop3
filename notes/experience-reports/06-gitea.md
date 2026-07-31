---
app: gitea
title: Gitea
version: "1.21.4"
upstream: https://gitea.io/
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
  nix-gen: {status: pass, template: go-source}
---

# Experience Report: Gitea

Self-hosted Git service. Packaged for Hop3 across the native, Docker and Nix build paths, and published in the signed catalog.

## What this app exercised

A Go source build with a JavaScript frontend, and an app whose own CLI must be reachable to create the administrator. It is the first consumer of `go-static-dirs` for source assets that are not the compiled frontend.

## What broke

- Pre-built Go binaries are expedient but not a long-term solution: while they offer a single static binary with no runtime dependencies and fast startup, they sacrifice reproducibility and architecture portability.
- INI config generation via [nix.config-files] works well for apps like Gitea that use traditional INI-style configuration.
- Gitea requires a specific `custom/conf/` directory structure for its configuration, which must be set up correctly in all deployment methods.
- Go apps with pre-built binaries have the most uniform experience across all deployment methods.

## What the platform gained

`${pkg}`, a stable binding for the application's own derivation, so a recipe can put the app's CLI on `PATH` without knowing the app id. `$out/bin` holds only the generated wrapper.

## Cost

Not recorded. The earlier reports did not track effort, and it cannot be reconstructed after the fact.

## Deployment variants

### Native

- **Builder/Toolchain:** local/generic
- **Addons:** PostgreSQL
- **Build steps:** Pre-built binary download (no source compilation)

### Docker

- **Base image:** debian:trixie-slim
- **Addons:** PostgreSQL

### Nix (hand-crafted)

- **Template equivalent:** prebuilt-binary
- **Addons:** PostgreSQL

### Nix (template-generated)

- **Template:** `go-source`
- **Key config:** app.ini config generation via [nix.config-files] (INI format)
- **Addons:** PostgreSQL

## Verification

`apps/gitea/check.py` runs against the deployed application and asserts, in order:

1. the probe-or-admin credential signs in
1. a wrong password is refused

It signs in with the credential Hop3 generated — the `[probe]` account where the recipe declares one, otherwise the `[admin]` credential, which is the weaker claim because the operator owns it.

## Reproduce

```bash
hop3 catalog install gitea
hop3 app check --app gitea
```

## Open

- **docker (not-attempted):** a recipe exists, but no run has measured it at the sign-in bar.
- **nix (not-attempted):** the hand-crafted recipe exists and has not been run at the sign-in bar.
- The earlier report's cross-method comparison is retained below but predates every status above:

  > All four methods are nearly equivalent in complexity since Gitea ships as a single binary. The only variation is how the app.ini configuration file is generated and placed in the custom/conf/ directory, which each method handles slightly differently. Note that the pre-built binary approach limits deployment to x86_64-linux; ARM and other architectures are not currently supported.

## Screenshots

![Sign-in page](images/gitea-01-login.png)
![After signing in](images/gitea-02-signed-in.png)
