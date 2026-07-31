---
app: isso
title: Isso
version: "0.14.0"
upstream: https://isso-comments.de/
languages: [python]
databases: []
in_catalog: true
report_status: draft
last_verified: 2026-07-31
verified_bar: authenticated

variants:
  native: {status: pass}
  docker: {status: not-attempted}
  nix: {status: not-attempted}
  nix-gen: {status: pass, template: python-venv}
---

# Experience Report: Isso

A lightweight commenting system, Disqus alternative. Packaged for Hop3 across the native, Docker and Nix build paths, and published in the signed catalog.

## What this app exercised

A comment widget whose `/` is an API rather than a page, and whose moderation dashboard is password-only — there is no account to name.

## What broke

- The Python venv template works cleanly for Isso with no special workarounds needed.
- Isso requires a specific Origin HTTP header on all requests, which means generic HTTP health checks return 400. Test validations must account for this.
- SQLite-based apps are the simplest to deploy since they eliminate all database provisioning and connection configuration.
- Running isso behind gunicorn is the standard production pattern and maps naturally to the python-venv template.

## What the platform gained

Not yet written — the earlier report did not record whether this application forced a change to Hop3 or merely confirmed one.

## Cost

Not recorded. The earlier reports did not track effort, and it cannot be reconstructed after the fact.

## Deployment variants

### Native

- **Builder/Toolchain:** local/python
- **Addons:** None
- **Build steps:** pip install

### Docker

- **Base image:** debian:trixie-slim
- **Addons:** None

### Nix (hand-crafted)

- **Template equivalent:** python-venv
- **Addons:** None

### Nix (template-generated)

- **Template:** `python-venv`
- **Key config:** isso + gunicorn packages, config.cfg generation
- **Addons:** None

## Verification

`apps/isso/check.py` runs against the deployed application and asserts, in order:

1. the admin dashboard is password-protected
1. the probe-or-admin password signs in
1. a wrong password is refused

It signs in with the credential Hop3 generated — the `[probe]` account where the recipe declares one, otherwise the `[admin]` credential, which is the weaker claim because the operator owns it.

## Reproduce

```bash
hop3 catalog install isso
hop3 app check --app isso
```

## Open

- **docker (not-attempted):** a recipe exists, but no run has measured it at the sign-in bar.
- **nix (not-attempted):** the hand-crafted recipe exists and has not been run at the sign-in bar.
- The earlier report's cross-method comparison is retained below but predates every status above:

  > All methods work well for Isso given its simplicity (Python + SQLite). The only quirk is the HTTP 400 response without an Origin header, which affects testing validation across all methods equally rather than being specific to any one deployment approach.

## Screenshots

![Sign-in page](images/isso-01-login.png)
![After signing in](images/isso-02-signed-in.png)
