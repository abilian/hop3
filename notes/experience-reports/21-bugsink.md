---
app: bugsink
title: Bugsink
version: "2.1.2"
upstream: https://www.bugsink.com/
languages: [python]
databases: [postgres]
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

# Experience Report: Bugsink

Self-hosted error tracking, Sentry SDK-compatible. Packaged for Hop3 across the native, Docker and Nix build paths, and published in the signed catalog.

## What this app exercised

Two processes from one recipe: a web worker and `snappea`, a background queue that keeps its own separate database. It is also the app that showed `[run.workers]` and a second `migrate --database=` are both needed before a post-login page works.

## What broke

Everything below is from the Nix template variant; the native one has been
clean.

**The bootstrap had nowhere to run.** A Nix app's build artifact reported the
read-only store path as its working directory, so `[run] before-run` — where
every native recipe keeps its first-run setup — could not be used at all. The
recipe compensated with a `pre-exec` block in the generated wrapper that
re-implemented part of the setup and skipped the rest.

**Two different secrets, both unstable.** `SECRET_KEY` was `$(head -c 32
/dev/urandom | base64)` in the wrapper's exports, which the wrapper re-evaluates
on *every start* — a new Django signing key per restart, invalidating every
session. Separately, `pre-exec` minted its own key into `bugsink_conf.py`, which
lives under `src/` and is wiped and regenerated on each deploy.

**No administrator was ever created**, so the smoke test reported "the sign-in
did not establish a session" against an application that was working correctly
and simply had no account.

**`psycopg` could not load `libpq`.** Once `before-run` worked, `migrate` died
with `ImproperlyConfigured: Error loading psycopg2 or psycopg module`. The
recipe declares `nix-runtime-libs`, but that became a single `LD_LIBRARY_PATH`
export *inside the wrapper* — so the app process had the libraries and nothing
else did. The same failure then reappeared one layer along, in
`[probe].create`, because the create commands did not receive the artifact's
runtime environment either.

**`DATABASE_URL` was composed in `[nix.env-exports]`**, which is also
wrapper-only. `[probe].create` had `PGUSER` and `PGHOST` but not the URL, and
Django failed building a connection.

## What the platform gained

`before-run` for Nix applications now runs in the app's own directory with the artifact's runtime environment applied (`working_dir`, and `nix-runtime-libs` reaching more than the wrapper). Before that a Nix app had nowhere to run a first-run bootstrap, and psycopg could not load `libpq` outside the wrapper.

## Cost

Most of the time went to two platform gaps rather than the app: `before-run` had no usable working directory for a Nix app, and the declared runtime libraries reached only the wrapper.

## Deployment variants

### Native

Not yet described.

### Docker

Not yet described.

### Nix (hand-crafted)

Not yet described.

### Nix (template-generated)

- **Template:** `python-venv`

## Verification

`apps/bugsink/check.py` runs against the deployed application and asserts, in order:

1. the probe-or-admin credential signs in
1. a wrong password is refused

It signs in with the credential Hop3 generated — the `[probe]` account where the recipe declares one, otherwise the `[admin]` credential, which is the weaker claim because the operator owns it.

## Reproduce

```bash
hop3 catalog install bugsink
hop3 app check --app bugsink
```

## Open

- **docker (not-attempted):** a recipe exists, but no run has measured it at the sign-in bar.
- **nix (not-attempted):** the hand-crafted recipe exists and has not been run at the sign-in bar.

## Screenshots

![Sign-in page](images/bugsink-01-login.png)
![After signing in](images/bugsink-02-signed-in.png)
