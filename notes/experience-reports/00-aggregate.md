# Aggregate Experience Report: Packaging 20 Applications for Hop3

**Status:** Draft (0.6)
**Last updated:** 2026-07-31

## Overview

Twenty open-source applications are packaged for Hop3 and published in the signed catalog. Each is packaged for up to four build paths — native (local builder), Docker, hand-written Nix, and Nix generated from a template — and each carries a `check.py` that signs in through the application's own authentication and confirms a wrong password is refused.

Packaging is system-validation work rather than a catalogue of business software. Every application in the set was chosen to stress a different edge of the platform, and the per-app reports record which edge and what it cost. Where an app merely confirmed existing behaviour, its report says so.

## Application coverage

The table is derived from the reports' own headers, which `hop3-tools catalog reports` checks against the recipes — so it cannot drift from them silently. `—` means a recipe exists and no run has measured it at the sign-in bar; `n/a` means there is no recipe for that variant.

| App | Language | Database | Native | Docker | Nix | Nix-gen |
|-----|----------|----------|--------|--------|-----|---------|
| BookStack | php | mysql | pass | — | — | pass |
| Bugsink | python | postgres | pass | — | — | pass |
| Dolibarr | php | postgres | pass | — | — | **fail** |
| Easy!Appointments | php | mysql | pass | — | n/a | — |
| Forgejo | go | postgres | pass | — | — | pass |
| Gitea | go | postgres | pass | — | — | pass |
| Invoice Ninja | php | mysql | pass | — | — | — |
| Isso | python | none | pass | — | — | pass |
| Kanboard | php | mysql | pass | — | — | **fail** |
| Keycloak | java | postgres | pass | — | — | pass |
| LimeSurvey | php | postgres | pass | — | — | — |
| Matomo | php | mysql | pass | — | — | **fail** |
| Mattermost | go | postgres | pass | — | — | **fail** |
| Miniflux | go | postgres | pass | — | — | pass |
| Nextcloud | php | mysql | pass | — | n/a | **fail** |
| Paheko | php | none | pass | — | — | **fail** |
| Radicale | python | none | pass | — | — | pass |
| Uptime Kuma | node | none | pass | n/a | n/a | n/a |
| Vikunja | go | postgres | pass | — | — | **fail** |
| WordPress | php | mysql | pass | — | n/a | pass |

**Languages:** php (10), go (5), python (3), java (1), node (1)
**Databases:** postgres (9), mysql (7), none (4)

Five applications were packaged, reported, and later dropped from the corpus — Adminer, Focalboard, Grafana, Jenkins and Wiki.js. Their reports are kept under `withdrawn/`, marked `report_status: withdrawn`, because the packaging work was real even though the applications are no longer advertised.

## What the numbers mean, and what they do not

**Native is the variant the catalog publishes**, and it is the only one measured at the sign-in bar across the whole set. The most recent complete recorded run was 19 of 20; the twentieth (Matomo) failed on catalog content that predated its own fix and passed once republished. No single recorded run has yet been all-green, and this report does not round that up. The gap is bookkeeping: a verification claim resting on "each of them passed at some point" is a weaker object than one resting on a run that can be pointed at.

**Nix-gen is 9 of 19** on a clean-server run: 9 pass, 7 fail, 3 the run could not reach a verdict on. The failures are not seven separate problems. Six of the seven are the same one — the application deploys and is never *installed*, because until 2026-07-31 a Nix app had nowhere to run a first-run bootstrap. Each report's **Open** section names its own case.

**Docker and hand-written Nix are unmeasured.** Recipes exist for nearly every app; no run has measured either at the sign-in bar. Earlier versions of these reports recorded both as "Passing", which is the specific rot this format exists to prevent: those statuses were asserted, not observed. `not-attempted` is the honest value and it is deliberately uncomfortable.

## The bar, and why it moved

For most of this corpus's life, "passing" meant the application deployed and answered HTTP 200. That bar was retired after a majority of the catalog was found to clear it while being impossible to log into: apps served their login page perfectly and rejected every credential. Some of those failures were the platform's, some the recipes', and one was the checking library posting an empty form body — the same symptom for all three.

Reports now name the bar they were verified at, in a header field the checker reads:

| Bar | Meaning |
|-----|---------|
| `http-status` | returned 200 — **not sufficient** for a catalog app |
| `http-content` | served its own content (a `contains` assertion) |
| `authenticated` | signed in through the app's own auth; a wrong password was refused |

An advertised application may not be reported `final` on anything less than `authenticated`, and the checker enforces it.

One gap remains open at the platform level: `[healthcheck].contains` is declared by no recipe in the corpus, and a deploy currently treats any status line as "serving". So the "App is now running" a deploy prints is satisfied by a 500. Until that changes, a deploy's own report of success is a weaker claim than these reports are.

## Recurring technical findings

The per-app reports carry the detail; these are the patterns that showed up in more than one.

**A credential is not injected until something maps it.** Hop3 generates an administrator password, stores it encrypted, and injects `HOP3_ADMIN_*`. An application reads whatever *it* reads, and the mapping is the recipe's job (`[env.computed]`). Where the mapping was missing, the recipe usually still carried a literal default — so the deployed application had an administrator whose password was published in the repository, while the operator was handed one that did not work. The smoke test reported only the second half of that. Four recipes were in this state.

**A secret evaluated by the wrapper is a secret that rotates.** Values in `[nix.env-exports]` are shell expressions re-evaluated on every start. Several recipes minted signing keys there with `$(head -c 32 /dev/urandom | base64)`, which silently invalidates every session on restart and, for the forges, makes 2FA secrets and stored credentials undecryptable. Generated-once `[env]` secrets are the mechanism; the shell is not.

**The generated wrapper is not the only thing that runs the app's code.** `[run] before-run` and the `[admin]`/`[probe]` create commands execute directly. Anything that lives only in the wrapper — `LD_LIBRARY_PATH` from `nix-runtime-libs`, a composed `DATABASE_URL` — is absent there, and the failure looks like a broken application rather than a missing environment.

**PHP `__DIR__` resolves symlinks**, so a Nix store path reached through one lands back in the read-only store. `needs-writable-dir` copies the tree instead. The copy's *timing* is the open question: it happens when the app starts, which is after `before-run`, so an application whose bootstrap needs its own code cannot use that hook yet.

**An app's binary is rarely named after the app.** `buildGoModule` names it after the module path element (`forgejo.org`, `miniflux.app`), and `$out/bin` holds only the generated wrapper, which execs one fixed subcommand. `${pkg}` is the stable binding for the application's own derivation.

**Multi-process applications are under-served.** Bugsink needs a `snappea` worker and a second `migrate --database=` before any post-login page works; Nextcloud wants a cron worker; Invoice Ninja wants a queue. `[run.workers]` expresses the processes, but not per-process environment, ports, or limits.

## Reproducibility tiers

Every tier builds in a sealed sandbox: the dependency set is vendored into a fixed-output derivation from a committed lockfile, so the package manager runs offline. What the tier ranks is provenance, not hermeticity.

| Tier | Method | Rebuilds identically? | Auditable to source? | Multi-arch? |
|------|--------|-----------------------|----------------------|-------------|
| 1 | nixpkgs package | yes | yes | yes |
| 2 | source build against a committed lockfile | yes | yes | one arch per lockfile |
| 3 | pre-built upstream artefact (`fetchurl`) | yes | no | **no** |

The pre-built-binary problem earlier drafts described has largely been worked through: Gitea, Forgejo, Miniflux and Vikunja are compiled from source with `go-source`, and Mattermost and Keycloak are `nixpkgs-wrapper`. Run `hop3-tools nix tiers apps/real-apps-nix-gen` for the current split, and see ADR 008 for the assessment.

## Open

- **No recorded all-green run.** Every application has been seen green; no single run has been all-green and saved. That artefact is outstanding, and it is what this report's headline number should eventually rest on.
- **Six nix-gen applications await one decision** — where the writable tree is materialised — rather than six separate fixes.
- **Docker and hand-written Nix are unverified** at the sign-in bar across the whole corpus.
- **Two packaging defects** are not bootstrap gaps and need build work: Paheko's Nix package does not carry its whole application tree, and Vikunja's frontend derivation does not build.
- **Two applications ship no built frontend** under Nix — Easy!Appointments and Isso — because the `php-app` and `python-venv` templates have no frontend build phase. Both serve a 200 whose JavaScript 404s, and their `contains` assertions pass on it.
- **The analysis sections above are being revised** against the current corpus. The coverage table and the statuses are current; the surrounding prose is catching up.
