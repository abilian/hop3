---
app: invoice-ninja
title: Invoice Ninja
version: "5.8.37"
upstream: https://invoiceninja.com/
languages: [php]
databases: [mysql]
in_catalog: true
report_status: final
last_verified: 2026-07-31
verified_bar: authenticated

variants:
  native: {status: pass}
  nix: {status: pass}
  nix-gen: {status: pass, template: php-app}
---

# Experience Report: Invoice Ninja

Free open-source invoicing platform.

## What this app exercised

A Laravel application whose UI is a Flutter canvas, so nothing a selector can reach. It probes the boundary of browser-driven verification. The boundary is declared; workarounds stop there.

## What broke

**No account was ever created**, so `POST /api/v1/login` answered 401 on an application that looked deployed and healthy. The migration that should have preceded it ran as `artisan migrate --force 2>/dev/null || true`, hiding its own failure.

**`APP_URL` pinned to localhost put `/` in a redirect loop.** Laravel derives the scheme and host of every redirect it issues from that value; Chromium gave up with `ERR_TOO_MANY_REDIRECTS` while the recipe's own `contains` assertion on `/login` passed throughout.

**Invoice Ninja authenticates on the email**, and the generated variant had acquired a `username` the native recipe deliberately omits, which a credential reader then prefers.

## What the platform gained

The screenshot harness's `unsupported` declaration: a way to say *this application cannot be driven by a browser, and here is why*. It isn't a gap. Radicale uses it for a different reason.

## Deployment variants

**Native** rebuilds the frontend with npm; the **Nix** variants rely on the committed Flutter bundle. Each variant ships something different, and both pass.

## Verification

`apps/invoice-ninja/check.py` signs in with the `[admin]` credential, and confirms a wrong password is refused. It has no `[probe]` account, so it signs in as the operator's administrator: the weaker claim, since that password can be changed out from under it.

## Reproduce

```bash
hop3 catalog install invoice-ninja
hop3 app check --app invoice-ninja
```

## Open

- **nix, nix-gen:** the sign-in page is photographed; there is no signed-in shot. The Flutter canvas offers no DOM inputs a selector can reach: declared `unsupported`, not a gap. `check.py` signs in over HTTP and is unaffected.

## Screenshots

![Sign-in page](images/invoice-ninja-01-login.png)
