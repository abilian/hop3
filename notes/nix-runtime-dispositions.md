# Nix runtime: per-application dispositions (M2.3)

**Status:** partial — covers the 20-application benchmark corpus. **Updated:** 2026-07-30.
**Source:** `notes/benchmarks/2026-07-28-matrix.jsonl`, a blank-slated four-variant run. Tiers from `hop3-tools nix tiers`.
**Why this exists:** M2.3 is a version declaration over the Nix runtime, and the deliverable is a *stated disposition per application*, not a green board. A milestone requiring everything to be green invites either a long tail of marginal work or a quiet redefinition of the corpus; a milestone requiring every application to have a recorded disposition can be finished, and can be checked by someone else.

## The result

**Zero Nix runtime failures.** Over the benchmark corpus the generated-recipe path ran 20 of 20, and the hand-written path 15 of 15 with 5 applications carrying no hand-written recipe. Every failure in that run was on the `native` variant (`isso`, `radicale`, `searxng`) and none of them concerns the Nix runtime.

This supersedes the red list carried in earlier planning notes (`easy-appointments`, `wordpress`, `nextcloud`, `forgejo`, `etherpad`). Of those, **wordpress, nextcloud and etherpad all run green** on the generated path in this run; the other two are not members of the benchmark corpus, so this run says nothing about them either way and they are listed as pending below.

## Dispositions

`no-recipe` in the *hand-written* column is not a gap. The generated path is the supported one; a hand-written expression exists only where an application needed control a template could not express, and its absence is the template set doing its job.

| Application | Template | Hand-written (`nix`) | Generated (`nix-gen`) | Disposition |
|---|---|---|---|---|
| `bookstack` | php-app | ok | ok | runs (both paths) |
| `bugsink` | python-venv | ok | ok | runs (both paths) |
| `directus` | node-pnpm-install | no-recipe | ok | runs (generated); hand-written recipe **not required** |
| `etherpad` | node-prebuilt | no-recipe | ok | runs (generated); hand-written recipe **not required** |
| `gatus` | go-source | ok | ok | runs (both paths) |
| `gitea` | go-source | ok | ok | runs (both paths) |
| `invoice-ninja` | php-app | ok | ok | runs (both paths) |
| `isso` | python-venv | ok | ok | runs (both paths) |
| `jenkins` | java-war | ok | ok | runs (both paths) |
| `keycloak` | nixpkgs-wrapper | ok | ok | runs (both paths) |
| `matomo` | php-app | ok | ok | runs (both paths) |
| `miniflux` | go-source | ok | ok | runs (both paths) |
| `nextcloud` | php-app | no-recipe | ok | runs (generated); hand-written recipe **not required** |
| `owncast` | go-source | ok | ok | runs (both paths) |
| `radicale` | python-venv | ok | ok | runs (both paths) |
| `searxng` | python-venv | no-recipe | ok | runs (generated); hand-written recipe **not required** |
| `stirling-pdf` | java-gradle | ok | ok | runs (both paths) |
| `vikunja` | go-source | ok | ok | runs (both paths) |
| `wiki-js` | node-prebuilt | ok | ok | runs (both paths) |
| `wordpress` | php-app | no-recipe | ok | runs (generated); hand-written recipe **not required** |

## What this does not cover

- **The corpus beyond the benchmark set.** There are 31 generated recipes and 31 hand-written ones; this run exercised 20 applications. The remaining recipes have no recorded disposition and are the honest gap in M2.3.
- **`forgejo` and `easy-appointments`**, named as red in earlier notes and absent from this corpus. `forgejo`'s reported symptom was a 180-second health-check timeout, which is the exact signature of the closure guard failing to fire — see [plan 30](../local-notes/plans/30-nix-runtime-1.0.md). Its disposition should not be decided before that guard is confirmed working, or the wrong defect gets fixed.
- **Anything about builds.** A running application says nothing about whether its build is reproducible; that is measured separately and reported in the technical report's §6.2.

## Standing rule

An application's disposition is one of **runs**, **fix** (ours, with the defect named), **defer-upstream** (theirs, with the blocker named), or **drop** (with the reason). "Not tested recently" is not a disposition; it is the absence of one, and this document says so where that is the case rather than leaving a blank.
