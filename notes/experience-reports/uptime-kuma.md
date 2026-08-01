---
app: uptime-kuma
title: Uptime Kuma
version: "2.4.0"
upstream: https://uptime.kuma.pet/
languages: [node]
databases: []
in_catalog: true
report_status: final
last_verified: 2026-07-31
verified_bar: authenticated

variants:
  native: {status: pass}
  nix: {status: no-recipe, reason: "superseded in practice by the template variant; no recipe here"}
  nix-gen: {status: no-recipe, reason: "no template recipe in the corpus"}
---

# Experience Report: Uptime Kuma

Self-hosted uptime monitoring with a web UI and status pages.

## What this app exercised

An app that authenticates over socket.io rather than HTTP, so its check drives the application's own bundled client through node.

## What broke

**The smoke test accused a working application for a week.** It reported "the credential Hop3 generated was refused"; the credential signs in through a browser without trouble. The probe drives the app's own bundled socket.io client through node, and every wait in it resolved on its own timeout:

- the connect wait resolved whether or not a socket opened;
- the next wait left `offered` as `null`, and the check asked only whether it was `'setup'`: `null` is not `'setup'`, so *"the server offers a login, not its setup wizard"* passed **without a socket ever being opened**;
- the login then timed out, and a timeout was returned as `false`, which the check rendered as a refusal.

Three silent fallbacks stacked into an accusation. Making them fail loudly also fixed the app: the probe had been emitting `login` before the server announced `loginRequired`, and a wait that must succeed cannot race ahead of it.

**The probe account was created only when the admin was.** `createProbeUser()` sat after an early `return` in the branch that creates the administrator, so any instance with an existing user row got no probe, undetectably, because nothing verified it.

**The JavaScript lived inside a Python string.** The probe was an embedded literal in `check.py`; a `\'` in the Python source arrived at node as a bare quote and killed the whole probe with a `SyntaxError`, after a full deploy. It is a `scripts/probe.js` file now, which is what `node --check` can read.

## What the platform gained

The catalog driver's separation of "the run could not verify this" from "this application failed" — the vocabulary LimeSurvey's browser-only sign-in introduced — hardened here from the opposite direction: a probe whose silent fallbacks were converting "unverified" into a false "failed".

## Deployment variants

Node, no addon, and no template-generated variant. It authenticates over socket.io rather than a form, so its check drives the app's own bundled client through node; the only application in the corpus verified that way.

## Verification

`apps/uptime-kuma/check.py` signs in as the `[probe]` account, which Hop3 owns and rotates, over socket.io — driving the application's own bundled client through node (`scripts/probe.js`), since Uptime Kuma has no form to post — and confirms a wrong password is refused.

## Reproduce

```bash
hop3 catalog install uptime-kuma
hop3 app check --app uptime-kuma
```

## Open

- **No signed-in screenshot.** Uptime Kuma authenticates over socket.io rather than a form, so the browser harness cannot drive it and says so rather than photographing the login page twice. Its sign-in is verified by the node probe instead.
- **Only one variant exists.** Native is the whole of this app's coverage: there is no hand-written Nix recipe and no template one.

## Screenshots

![Sign-in page](images/uptime-kuma-01-login.png)
