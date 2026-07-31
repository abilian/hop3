---
app: paheko
title: Paheko
version: "1.3.15"
upstream: https://paheko.cloud/
languages: [php]
databases: []
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

# Experience Report: Paheko

Nonprofit accounting and association management. Packaged for Hop3 across the native, Docker and Nix build paths, and published in the signed catalog.

## What this app exercised

A PHP application that resolves its own public URL from `$_SERVER`, which is wrong behind a TLS-terminating proxy, and whose login form routes on the submit button's name.

## What broke

**The login form was never processed.** The sign-in POST returned 200 with the form re-rendered and no error text. A correct password, a wrong password, and a deliberately *omitted* CSRF token all produced identical responses — the signature of a form that was never handled rather than one that was rejected. The cause was that Paheko routes on the submit control's name (`$form->runIf('login', …)`), and the check posted only the form's hidden fields. A browser sends the button it clicked; the check did not.

**It advertised itself over plain HTTP.** Paheko resolves its own public URL from `$_SERVER`, and behind Hop3 it is reached over HTTP by the proxy that terminates TLS — so it rendered `data-url="http://…"` on an HTTPS deployment. `HOP3_PUBLIC_URL` is injected for exactly this and the recipe was not using it. Fixing it did not fix the sign-in, which is worth recording: it was a real defect and a wrong hypothesis at the same time.

**The Nix package is incomplete.** The template variant fails with `require_once .../KD2/ErrorManager.php: No such file or directory` — the built package does not carry the whole application tree. No bootstrap change fixes that.

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

- **Template:** `php-app`

## Verification

`apps/paheko/check.py` runs against the deployed application and asserts, in order:

1. the probe-or-admin credential signs in
1. a wrong password is refused

It signs in with the credential Hop3 generated — the `[probe]` account where the recipe declares one, otherwise the `[admin]` credential, which is the weaker claim because the operator owns it.

## Reproduce

```bash
hop3 catalog install paheko
hop3 app check --app paheko
```

## Open

- **nix-gen (fail):** the Nix package does not carry the whole application tree (`require_once .../KD2/ErrorManager.php` fails), which no bootstrap fixes.
- **docker (not-attempted):** a recipe exists, but no run has measured it at the sign-in bar.
- **nix (not-attempted):** the hand-crafted recipe exists and has not been run at the sign-in bar.

## Screenshots

![Sign-in page](images/paheko-01-login.png) ![After signing in](images/paheko-02-signed-in.png)
