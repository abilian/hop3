---
app: radicale
title: Radicale
version: "3.2.3"
upstream: https://radicale.org/
languages: [python]
databases: []
in_catalog: true
report_status: final
last_verified: 2026-07-31
verified_bar: authenticated

variants:
  native: {status: pass}
  nix: {status: pass}
  nix-gen: {status: pass, template: python-venv}
---

# Experience Report: Radicale

A simple CalDAV and CardDAV server.

## What this app exercised

Authentication with no user store: an account is a line in an htpasswd file, so both accounts are created by writing that file. Also the app that showed a file the server reads at startup cannot be created by a post-deploy command.

## What broke

**It served every calendar and address book to anyone who asked.** `[auth] type` was `${RADICALE_AUTH_TYPE:-none}` and nothing ever set it otherwise, so the deployed server authenticated nobody. Every instrument the project had reported it green, because a server that authenticates nobody answers every request successfully. The only assertion that could catch it did: *a wrong password returned 200, not 401*.

The config was also written once and left alone, so a deployment that had ever run open stayed open for the rest of its life. It is rewritten on every start now, and the auth type is spelled out where no environment can switch it off.

**There is no signed-in screenshot to take.** Radicale authenticates over HTTP Basic and its `.web` interface renders identically whether or not a credential was sent; the two images were once byte-identical and were being counted as two.

## What the platform gained

The screenshot harness no longer photographs a page it has not signed into; Radicale's two images were byte-identical and were being filed as proof.

## Deployment variants

Available as a top-level nixpkgs package, so the **Nix** variants wrap it rather than building anything. File-based storage and no addon. Accounts are lines in an htpasswd file (there is no user CLI), so `create` writes a bcrypt hash directly, which is why the derivation puts a `python3` carrying bcrypt on the app's PATH in its own right.

## Verification

`apps/radicale/check.py` signs in with the `[probe]` account, which Hop3 owns and rotates, and confirms a wrong password is refused.

## Reproduce

```bash
hop3 catalog install radicale
hop3 app check --app radicale
```

## Open

- **nix:** the sign-in page is photographed; there is no signed-in shot, deliberately. Radicale authenticates over HTTP Basic and its `.web` interface renders identically whether or not a credential was sent.
- **nix-gen:** the sign-in page is photographed; there is no signed-in shot, deliberately. Radicale authenticates over HTTP Basic and its `.web` interface renders identically whether or not a credential was sent; the two images were once byte-identical and were being counted as 2 of 2.

## Screenshots

![Sign-in page](images/radicale-01-login.png)

Only the sign-in page. Radicale's `.web` interface renders identically once authenticated, so a second image would prove nothing: the pair that used to be here was byte-identical.
