---
app: miniflux
title: Miniflux
version: "2.1.1"
upstream: https://miniflux.app/
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

# Experience Report: Miniflux

Minimalist and opinionated RSS reader. Packaged for Hop3 across the native, Docker and Nix build paths, and published in the signed catalog.

## What this app exercised

An app that creates its own administrator at first start from injected environment variables, with no command for Hop3 to run.

## What broke

- Simplest Go app to package: single binary with environment-variable-only configuration.
- Native builds from source using make, but Nix uses a pre-built binary, showing how deployment methods can diverge in build strategy while producing the same result.
- DATABASE_URL is the only required configuration, making this app ideal for testing minimal PostgreSQL addon integration.

## What the platform gained

Not yet written — the earlier report did not record whether this application forced a change to Hop3 or merely confirmed one.

## Cost

Not recorded. The earlier reports did not track effort, and it cannot be reconstructed after the fact.

## Deployment variants

### Native

- **Builder/Toolchain:** local/generic
- **Addons:** PostgreSQL
- **Build steps:** Build from source (make)

### Docker

- **Base image:** debian:trixie-slim
- **Addons:** PostgreSQL

### Nix (hand-crafted)

- **Template equivalent:** prebuilt-binary
- **Addons:** PostgreSQL

### Nix (template-generated)

- **Template:** `go-source`
- **Key config:** Environment variable driven (no config file generation)
- **Addons:** PostgreSQL

## Verification

`apps/miniflux/check.py` runs against the deployed application and asserts, in order:

1. the probe-or-admin credential signs in
1. a wrong password is refused

It signs in with the credential Hop3 generated — the `[probe]` account where the recipe declares one, otherwise the `[admin]` credential, which is the weaker claim because the operator owns it.

## Reproduce

```bash
hop3 catalog install miniflux
hop3 app check --app miniflux
```

## Open

- **docker (not-attempted):** a recipe exists, but no run has measured it at the sign-in bar.
- **nix (not-attempted):** the hand-crafted recipe exists and has not been run at the sign-in bar.
- The earlier report's cross-method comparison is retained below but predates every status above:

  > All methods pass cleanly. Miniflux is the simplest Go app in the set due to its single-binary, env-var-only design, making it a good baseline for testing Go deployment pipelines. The pre-built binary approach limits deployment to x86_64-linux; ARM and other architectures are not currently supported.

## Screenshots

![Sign-in page](images/miniflux-01-login.png)
![After signing in](images/miniflux-02-signed-in.png)
