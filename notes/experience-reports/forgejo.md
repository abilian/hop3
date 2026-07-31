---
app: forgejo
title: Forgejo
version: "14.0.3"
upstream: https://forgejo.org/
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

# Experience Report: Forgejo

Self-hosted Git service (community fork of Gitea). Packaged for Hop3 across the native, Docker and Nix build paths, and published in the signed catalog.

## What this app exercised

The same shape as Gitea, and the app that showed a Go binary is named after its module path (`forgejo.org`), not the project.

## What broke

Shared with Gitea, whose report describes the same four defects; only the last is specific to Forgejo.

**The admin bootstrap could not find the binary.** `[admin].create` was copied from the native recipe, which calls `./forgejo` — correct in a source tree that contains the binary, wrong when the command runs in the app's source directory and the binary is in the Nix store. It failed with `sh: ./forgejo: not found` after a 220-second build, and the deploy correctly refused to leave an app with no administrator.

**`$out/bin` holds only the generated wrapper**, which execs one fixed subcommand, so putting it on `PATH` does not help. The application's own derivation is a different store path.

**Three signing secrets rotated on every restart.** `SECRET_KEY`, `INTERNAL_TOKEN` and `JWT_SECRET` were minted with `$(head -c 32 /dev/urandom | base64)` inside a config file the wrapper rewrites at each start.

**The binary is called `forgejo.org`.** `buildGoModule` names the output after the module path element, not the project — the same reason Miniflux's binary is `miniflux.app`. Every `forgejo …` invocation in the recipe had to be `forgejo.org …`.

**Open registration.** `DISABLE_REGISTRATION = true` lives in the native recipe's `scripts/setup-config.sh`, and no Nix variant carries a `scripts/` directory — so the Nix builds deploy an internet-facing forge on which the first visitor can register.

## What the platform gained

Not yet written — the earlier report did not record whether this application forced a change to Hop3 or merely confirmed one.

## Cost

Not recorded. The earlier reports did not track effort, and it cannot be reconstructed after the fact.

## Deployment variants

### Native

Not yet described.

### Docker

Not yet described.

### Nix (hand-crafted)

Not yet described.

### Nix (template-generated)

- **Template:** `go-source`

## Verification

`apps/forgejo/check.py` runs against the deployed application and asserts, in order:

1. the probe-or-admin credential signs in
1. a wrong password is refused

It signs in with the credential Hop3 generated — the `[probe]` account where the recipe declares one, otherwise the `[admin]` credential, which is the weaker claim because the operator owns it.

## Reproduce

```bash
hop3 catalog install forgejo
hop3 app check --app forgejo
```

## Open

- **docker (not-attempted):** a recipe exists, but no run has measured it at the sign-in bar.
- **nix (not-attempted):** the hand-crafted recipe exists and has not been run at the sign-in bar.

## Screenshots

![Sign-in page](images/forgejo-01-login.png) ![After signing in](images/forgejo-02-signed-in.png)
