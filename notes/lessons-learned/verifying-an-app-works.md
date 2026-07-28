# Lessons Learned: Verifying That an App Actually Works

**Updated**: 2026-07-28 - written after the catalog acceptance campaign (all 20 catalog apps installed by hand through the Web UI).

Every level of "it worked" we have trusted has, at some point, hidden a broken app. This file records where each level failed and what replaced it.

## The ladder of false greens

| Signal | What it actually proves | How it lied |
|---|---|---|
| `nix build` succeeds | The derivation evaluated and built | Redmine built fine and crash-looped on boot (bundler rejected the Gemfile pair). Gitea built fine and crash-looped on a missing locale dir. |
| The deploy returns success | A process started and bound a port | An app can bind its port and never finish importing its WSGI app. |
| `GET /` returns 200 | *Something* answered | A placeholder page, an error page, a setup wizard, or another app's content. Fixed by `[healthcheck].contains` — assert the app's own content. |
| The login page renders 200 | Static files are served | Bugsink served its login page while every post-login request 500'd — its worker process and queue DB were a second, unstarted service. Invoice-ninja served an SPA shell whose frontend bundle was absent. |
| A login attempt is accepted | Almost everything | Only if a *wrong* password is refused in the same run. |

**Rule:** the strongest cheap signal is *sign in with the credential the platform generated, then confirm a wrong password is refused.* That is what `check.py` does for every catalog app, and it runs at the end of every deploy — not as a separate harness someone has to remember.

## A check that cannot fail proves nothing

The first version of the negative assertion looked for a session cookie after a bad-password POST. Several apps set a session cookie *on the login page itself*, so the assertion passed for a rejected password. The check reported green while testing nothing.

Replace "did something cookie-ish happen" with **the same reachability test the positive assertion uses**: fetch a page that requires authentication and confirm it is refused. If the positive and negative assertions do not exercise the same code path, they are not each other's control.

Before adding an assertion, ask what would make it *fail*. If you cannot state that, the assertion is decoration.

## Verifying an app you cannot log into forever

An operator changes the admin password on day two, and the check can never run again. Options considered and rejected: skipping the check (a silent skip — forbidden), storing the operator's new password (we should not have it), reporting "NO CHECK" as a status (SF: "'NO CHECK' should not be a state").

**What works: a `[probe]` account.** Hop3-owned, non-privileged, password rotated by Hop3, created by the app's own user-creation CLI at deploy time. The check uses it when present and falls back to the admin credential otherwise, naming which account it used either way.

Two constraints learned the hard way:

- **Bootstrapping the probe account must be non-fatal.** The first version aborted the deploy when creation failed — taking down a perfectly working app because a *test* account could not be made.
- **It must be disable-able per app.** The security position is that platform access already implies access to all code, config and data, so a probe account adds little exposure — but that argument does not hold for a deployment with encryption at rest and third-party credentials, so the opt-out has to exist.

## Verify the effect, not the exit code

A bootstrap CLI can print an error and exit 0. Gitea's `admin user create` did exactly that (`admin` is a reserved name in gitea/forgejo), and the deploy recorded a credential for an account that never existed.

- Confirm the account exists; do not trust the return code.
- When a bootstrap command fails, **include its output in the error**. Reporting only "exit status 1" made nextcloud's failure undiagnosable for the whole campaign; the first run that echoed the command's output revealed `occ user:add` takes no `--email`.
- Never present a generated credential for an account whose creation failed. The credential row is created before the bootstrap runs, so this needs an explicit "not created" state, not an inference.

## Retry has to be first-class if you do not roll back

Hop3 deliberately does not roll back a failed deploy — the half-built state is diagnostic. But `catalog install` committed the app row *before* deploying, so a failed deploy left a row that refused every subsequent attempt with "already exists". The operator had an app they could neither use nor reinstall, and no stated way forward.

**The general shape:** any path that commits a record before the side effect succeeds must define what a second attempt does. "We don't roll back" is only a coherent position when paired with "so you can resume".

## Test-only conveniences that are really platform bugs

Twice in this campaign the check harness could not do something, and the correct fix was in the platform:

- The check could not sign in over HTTP because apps set `Secure` cookies. The fix was not a test flag — it was making **HTTPS the default**, because a real browser had exactly the same problem.
- The check deadlocked during nextcloud's install. The fix was not a longer timeout — PHP's built-in server is **single-threaded**, and Hop3 was running it with one worker, so any app that sub-requests itself hangs. Ten of the twenty catalog apps sit on that runtime.

When the harness struggles, ask whether a user would struggle identically. Usually they would.

## Related

- [`deployment-diagnostics.md`](./deployment-diagnostics.md) — making a failure legible once it happens.
- [`app-deploy-runtime-model.md`](./app-deploy-runtime-model.md) — deploy vs redeploy state transitions.
- [`web-auth-and-csrf.md`](./web-auth-and-csrf.md) — cookie/session pitfalls on Hop3's own dashboard.
