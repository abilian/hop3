---
app: easy-appointments
title: Easy!Appointments
version: "1.5"
upstream: https://easyappointments.org/
languages: [php]
databases: [mysql]
in_catalog: true
report_status: final
last_verified: 2026-07-31
verified_bar: authenticated

variants:
  native: {status: pass}
  nix: {status: no-recipe, reason: "superseded in practice by the template variant; no recipe here"}
  nix-gen: {status: fail}
---

# Experience Report: Easy!Appointments

Open source appointment scheduling.

## What this app exercised

Whether the sign-in bar can be met by an application that builds its login form in JavaScript. It is the corpus's answer to that: no, not yet, by either verification path.

## What broke

**The login form is built in JavaScript**, so the served page carries no inputs at all. An HTTP check cannot sign in, and this is the one application in the corpus where the browser harness cannot either: it fills the form, submits, and is still looking at it afterwards. The bootstrap reports success and the credential is reconciled; nothing has demonstrated the result.

**The git tag is not the release.** It omits both the minified frontend assets and `vendor/`, so a package built from it is missing part of the application.

**`BASE_URL` was built by hand as `http://${HOST_NAME}`**: right host, wrong scheme. The app constructs its login POST from that constant, so on an HTTPS site the browser was asked to submit over a scheme the page cannot use.

## What the platform gained

`unzip` on `buildComposerProject`'s `nativeBuildInputs` when the source is a zip, in the `php-app` template. Otherwise this app is a standing question rather than a contribution: it is the one application the sign-in bar cannot reach.

## Deployment variants

Every variant takes the upstream *release* archive rather than the git tag. It is a flat zip, so `source-root` is `"."`, and it already ships 27,549 `vendor/` entries, so composer is switched off; which in turn wanted `unzip` on `buildComposerProject`'s `nativeBuildInputs`, now supplied by the `php-app` template.

## Verification

`apps/easy-appointments/check.py` signs in with the `[admin]` credential, and confirms a wrong password is refused. It has no `[probe]` account, so it signs in as the operator's administrator: the weaker claim, since that password can be changed out from under it.

## Reproduce

```bash
hop3 catalog install easy-appointments
hop3 app check --app easy-appointments
```

## Open

- **nix-gen (fail):** the bootstrap runs and reports success (the schema is created and the admin is reconciled to the injected credential) but neither verification path completes. `check.py` defers to the browser because the served page carries no form inputs at all, and the browser fills the JavaScript-built form, submits, and is still looking at it afterwards. The application may well be correct; nothing has demonstrated it.

## Screenshots

![Sign-in page](images/easy-appointments-01-login.png)
![After signing in](images/easy-appointments-02-signed-in.png)
