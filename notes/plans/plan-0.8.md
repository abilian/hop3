# Plan: 0.8: the platform underneath the apps

**Created:** 2026-08-01. **Owner:** SF. **Target:** no fixed date; the release follows the checks in [Before tagging](#before-tagging) (set 2026-10-11; was the week of 2026-09-28, and September 2026 before that).
**Predecessor:** [`plan-0.7.x.md`](plan-0.7.x.md): fixes and polish on what 0.7 ships. Anything that repairs 0.7 belongs there; this file is for what 0.8 *adds*.
**Successor:** [`plan-0.9-plus.md`](plan-0.9-plus.md) (the queue behind this release), [`plan-0.9-per-app-users.md`](plan-0.9-per-app-users.md), and [`parked.md`](parked.md) (directions not scheduled).
**Sources:** the "After 0.7" list in [`../todo.md`](../todo.md), TR-03 §9 (Future Work), the draft and deferred ADRs, the per-app experience reports and their deferral records, the team's internal roadmap notes.

This file reads in time order: what is left to do first, with what it takes to do it; the decisions those tasks rest on; then what is done, briefly, at the end.

## Status, 2026-10-18

- **Release gate:** the catalog is published under `catalog/v1/`. A run of the published catalog (2026-10-18) and the tutorial suite (2026-10-18) pass on a remote server. Left: the full catalog run on a blank-slate server, `make test-e2e` on a quiet machine, the HTTPS login path, and SF's review of the release notes.
- **Headlines:** php-fpm (2) and local-source builds (3) are done. Per-app UID separation (1) ships its first two steps and rootd's caller check; per-app users move to 0.9. Installer composability (4) ships in part; the rest moves to 0.9.
- **Scope:** the second tier moved to 0.9 (2026-10-13, [below](#decided-the-second-tier-moves-to-09-2026-10-13)), and so did the rest of 0.8's open work (2026-10-19, [below](#decided-the-remaining-open-work-moves-to-09-2026-10-19)). 0.8 tags on its release checks alone.

## Before tagging

In order. An item names how to run it and what finishes it.

### Catalog versioning (design in [Catalog versioning](#decided-catalog-versioning-2026-10-13))

- [x] **The server checks the catalog `format`** (2026-10-13). `sync.py` `CATALOG_FORMAT`, read by the publisher too; a missing or unknown format is refused before the tree check, naming what it found, while the held catalog and serial stay. `CATALOG_SOURCE_URL` defaults to `…/catalog/v1/catalog.tar.gz`. No check that the URL's `v<N>` matches the index: the format check already refuses whatever this server cannot read. A URL naming an older format the server still reads is a valid choice.
- [x] **Server features and computed requirements** (2026-10-13). `server/catalog/features.py`: eleven features with their release and rule (`admin-verify` 0.7.3, `proxy-limits` 0.7.4, `php-fpm` and `document-root` 0.7.5, `proxy-deny`, `access-gate`, `scratch-volumes`, `nix-github-source`, `nix-local-source`, `nix-gem-cargo-hashes`, `nix-before-run` 0.8). `nix-before-run` reads the hand-written `hop3.nix`, the one rule that does. `build_index` writes `requires` into each entry; the loader reads it from the index; `catalog install` refuses a missing feature by name. Two changes from the design:
  - `requires_hop3` stays hand-written in `catalog.toml`, because servers before 0.8 read it from there and deriving it would mean rewriting signed recipe files. The publish refuses a value lower than the features need and prints the one to write. The catalog check found 11 recipes under-declared (paheko, wordpress, dolibarr, kanboard among them); their `catalog.toml` now say so.
  - No `features` in `hop3 status --json`: a refused install names the missing feature. Nothing reads the list yet.
  - The four recipes that declared 0.8 with no feature detected (2026-10-17): paheko-nix, radicale-nix and vikunja-nix write `before_run`, now `nix-before-run` (which also found five alpha recipes declaring nothing). forgejo-nixgen needs `go_1_25` from the default nixos-26.05 pin, which no rule reads; its `catalog.toml` says so.
- [x] **Publish `catalog/v1/`** (2026-10-18). `stage` reads the format from the built index and copies the signed artifacts to `public/catalog/v<format>/` and to the legacy `public/catalog/`. `curl -s https://apps.hop3.cloud/catalog/v1/catalog.tar.gz | tar xzO index.json` shows `"format": 1`, a `requires` list in every entry, and 54 entries.
- [x] **`hop3-test run --recipes published`** (2026-10-16; first runs on Docker 2026-10-16 and on a server 2026-10-18). The redeploy step is `hop3 app upgrade --app <name>`, an operator's redeploy of an installed app. The features the server is installed with are sized from the local checkout, since the server's list exists only after the install; a published app needing one it lacks is left out, by name. Screenshots moved into the harness (2026-10-17): `--screenshots` photographs each passed catalog recipe signed in, refused on Docker; an app whose sign-in only a browser can drive is reported as not verified (status `unverified`, which leaves the exit code alone) in a run without one, and fails if the browser cannot sign in.
  - The default, `local`, reads the sibling catalog checkout, as today. `published` reads the server's catalog.
  - The run calls `hop3 catalog refresh` on the target, lists the entries (`hop3 catalog list`), and selects by name and by `--status` (golden and beta only: alpha is not published).
  - Each app's `[test]` section is read from the server's extracted copy (`CATALOG_ROOT/<id>/hop3.toml`, over the target's `exec_run`), so the test describes the recipe that was installed.
  - The deploy step is `hop3 catalog install <id> --app <name>` in place of the tarball upload. Everything after it is the local run's code: validations, `check.py`, the redeploy, the write check, the bundle, teardown.
  - [x] `check-catalog.py` and `shoot-catalog.py` deleted from the catalog repository (2026-10-17); `redeploy-and-check.py` runs `hop3-test` in their place. The catalog README's promotion rule names the published run with `--screenshots` (2026-10-18).
  - Tests: selection from a stub catalog listing; the deploy command a published run issues; a `--status alpha` request refused with the reason.
- [x] **A run of the published catalog** (2026-10-18, run 1293): `uv run --with playwright hop3-test run --host <server> --recipes published --with all --screenshots` passed 54 of 54, golden and beta, each installed with `hop3 catalog install`, upgraded and checked again; 48 photographed signed in. The run before it failed wordpress-nixgen, whose probe script the recipe had never shipped. Its images showed mattermost's two Nix variants serving no web client since their import, with the REST check green. Both were fixed in the catalog and published before run 1293.

### Runs

- [ ] **A full catalog run on a blank-slate remote server**: `uv run hop3-test run --provider hetzner --host <throwaway box> --with all --from local --mode full`. Finished when the catalog's golden, beta and alpha tiers pass on the rebuilt box and its empty Nix store, last done on 2026-09-21. Without `--mode`, `run` takes the `smoke` profile (fast and P0 tests only), which is the nine Procfile fixtures: the runs of 2026-10-13 (run 1244) and 2026-10-19 (run 1295) that this item once recorded as the catalog run were those nine.
- [x] **The full tutorial suite on a remote server** (2026-10-18, run 1294): `uv run hop3-test run --host <server> --from local docs/tutorials` passed 35 of 35, the 2026-10-06 failures (rails, sinatra, jekyll, django, nestjs, nuxtjs, nix-gen-flask) included.
- [ ] **`make test-e2e` on a quiet machine** (one e2e session per machine).
- [x] **Re-record directus-nixgen's `node-deps-hash` on x86_64** (2026-10-17). Recorded from a cold build on an x86_64 Docker host. The build behind it then failed to compile `isolated-vm` 5.0.3, which uses `uint32_t` without including `<cstdint>`; the `node-pnpm-install` template now force-includes it for native addons, and the recipe passes, redeploy included. Alpha, so nothing to publish.
- [ ] **The HTTPS login path against a real admin domain.** Owed since ADR 042's fourth revision: only the SSH fallback has run end to end. On a server with an admin domain and a trusted certificate: `hop3 login`, then a read-only command, checking that it travels over HTTPS and not the SSH tunnel; then the same with the gated fixture `180-flask-gated`, which the runner includes only on such a server.

### Release notes

- [ ] **`CHANGES.md` reviewed as release notes**: it has grown by accretion over the cycle. Group by what an operator notices; every claim is something that shipped. Drafted 2026-10-18: highlights, what to do when upgrading from 0.7, then the entries by area (accounts, apps, PHP, Nix, proxies, backups, catalog, email, CLI, installation, documentation, the test harness). One claim corrected on the way: the access gate works on Caddy and Traefik, but the installer routes the admin domain on nginx only. Left (SF): the review.
- [x] **The isolation that remains open is stated** (2026-10-18, "Upgrading from 0.7" and the rootd entry): apps share one Unix user, so one app can read another's data and the control plane's, until 0.9 ([`plan-0.9-per-app-users.md`](plan-0.9-per-app-users.md)). App code can no longer reach root through rootd.
- [x] **The catalog change is stated** (2026-10-18, "Upgrading from 0.7" and the catalog entry): servers before 0.8 keep fetching the legacy path and are refused apps that need 0.8.

## Decided: catalog versioning (2026-10-13)

**A catalog and a recipe are versioned on different axes.** The format is the container: whether a server can read the catalog at all. A recipe's needs from the server are a separate question. They move every release without the format moving: paheko is a format-1 entry that needs php-fpm, which 0.7 does not have.

| Axis | Where | Answers | Changes when |
|---|---|---|---|
| `format` | signed `index.json`, and the URL | Can this server read this catalog at all? | The layout changes in a way an existing reader would misread |
| `serial` | signed `index.json` | Is this catalog newer than the one I hold? | Every publish (anti-rollback, ADR 049 F4) |
| `requires` | each entry, in the signed index | Does this server have what this app needs? | A recipe starts using a server feature |

**`format` is an integer. The server refuses one it does not know.** The publisher has written `"format": 1` since ADR 049 shipped, and no server reads it. The number moves only on an incompatible change. An addition an older reader can ignore (a new optional key in the index, a new file in an entry) leaves it alone, so readers ignore unknown keys and the publisher never removes or reinterprets one within a format.

**The format is also in the URL**: `catalog/v1/catalog.tar.gz`. A server derives its default source from the highest format it reads. When format 2 arrives, `make publish` writes `v2/` beside `v1/` for as long as servers that read only format 1 are supported, so those servers keep receiving updates. Retiring a format is a decision made at publication. An old server says so loudly when it meets a retired one. Neither needs a server release made after the fact.

**The publisher computes a recipe's needs as a list of named server features.** A hand-written `requires_hop3` is wrong as soon as someone forgets it: 36 entries declare one, and paheko, which needs php-fpm, does not. The publisher derives `requires` from the recipe, and `requires_hop3` from `requires`, for servers that predate feature names (0.7 reads `requires_hop3` and ignores `requires`). A feature has a name and no version, so the check holds where a version number misleads: a fix backported to a point release, a development build, a fork. The error names what is missing.

**The legacy path** (`/catalog/catalog.tar.gz`, what 0.7 servers fetch) receives a copy of `v1/` while the layout is unchanged. Losing 0.7 servers is accepted (SF): an entry that requires 0.8 is refused there. Nothing is kept for them.

**A run of the published catalog is a flag on `hop3-test run`**, not a second runner: `check-catalog.py` and the harness drifted before (the probe credential, the check port).

Built; [ADR 049](../adrs/049-catalog-distribution.md#versioning) records the design.

## Decided: per-app users in 0.9 (2026-10-11)

0.8 ships without them, and rootd's caller check closes the worst consequence (app code reaching root). Doing the runtime alone would leave build-time recipe code running as `hop3` and change every app's file ownership twice. Work plan: [`plan-0.9-per-app-users.md`](plan-0.9-per-app-users.md); every switch of user goes through hop3-rootd, no sudo.

## Decided: the second tier moves to 0.9 (2026-10-13)

SF cut the second tier: email beyond the harness, the control-plane audit log, monitoring and resource metrics, the rest of the command surface (ADR 047 and the command-manifest ADR), the `hop3-catalog-core` extraction, and catalog growth. Each is in [`plan-0.9-plus.md`](plan-0.9-plus.md#cut-from-08-2026-10-13), with the detail it had here. 0.8 kept the remainder of headline 4 and the gate's remaining items until 2026-10-19 (below).

## Decided: the remaining open work moves to 0.9 (2026-10-19)

SF moved what was left in 0.8's scope: the rest of headline 4 (the installer's `--with=nodejs-*|pnpm|headless-browsers|latex`, a per-app package manager version, the kernel sysctls) and the gate's remaining items (bearer tokens for scripts, Caddy and Traefik in the installer, per-app roles, a regular run of the gate). Each is in [`plan-0.9-plus.md`](plan-0.9-plus.md#cut-from-08-second-round-2026-10-19), with the detail it had here.

Every one of them changes the server, so each would have sent the release back through the blank-slate catalog run and the tutorial run. No published recipe needs any of them. What 0.8 ships without them: headline 4 in part, a sign-in gate that a server installed with Caddy or Traefik cannot use yet (the release notes say so), a deployer role that reaches every app, and Etherpad's pnpm-10 workarounds. A native Node app in 0.8's catalog, or the gate on Caddy in this release, would each have pulled one item back in.

## The theme

0.7 answered a question about applications: *do real self-hosted apps deploy on Hop3 and actually work?* Twenty of them do, verified by signing in. The same campaign produced a long list of things the *substrate* cannot yet express or protect, and almost every item in this plan was found by an application running into it. **0.8 is about the platform underneath the apps**, through four headline items:

1. **Apps are not isolated from each other or from the control plane.** Every native app runs as `hop3`, so any app could reach rootd and pass its credential check, read every other app's environment and addon credentials, and interfere with a sibling's resources.
2. **PHP had no production runtime**: ten catalog apps served through a single-threaded development server.
3. **The generator only packaged software fetched from elsewhere**, so an operator's own application had no route to the Nix path.
4. **Toolchain versions were the server's choice**, not the app's.

Absent on purpose: nothing watches a process that dies (ADR 029), and multi-process applications rely on convention alone (ADR 038). Both are in [`parked.md`](parked.md); each would change the platform's shape.

**What makes 0.8 a good release:** an operator can be handed the platform with one stated caveat. An app that cannot reach root (reading its neighbour's data waits for 0.9). PHP served properly. A generator packages your own code. An app chooses its Node version. An operator can ask the installer for Rust, Clojure or Elixir. Roles and the sign-in gate add the other half: the operator decides who reaches each app.

## After 0.8

The queue behind this release is [`plan-0.9-plus.md`](plan-0.9-plus.md). It starts with what was cut from 0.8: the second tier (email, the audit log, monitoring, the command surface, catalog-core, catalog growth), then the rest of headline 4 and of the sign-in gate. Per-app users with build-time isolation come next. Then come recipe upgrades for installed catalog applications, SSO and MFA, the isolation ADR and the alternative backends behind it, the runtime-stack replacement (ADR 023), deployment strategies, backups phases 2 and 3, supply-chain attestation, and a tail of smaller items. ADR 055 moves from Proposed to Accepted once that work settles its open questions.

Directions *not* scheduled (the agent model, multi-component applications, the generator's second output target, the classifier extraction, and portability as a nightly property) are in [`parked.md`](parked.md), with the reason each is held back.

## Done

### Headline 1: per-app UID separation, first steps (ADR 055)

- **State is kept across a redeploy** (2026-09-28/29): `scratch` volumes, volumes linked after the build, a harness that fails an app writing into `src/` and redeploys every app. All 20 golden, all 34 beta Nix variants and 54 of 55 alpha recipes pass on Docker, redeploy included. Two things are not covered: the Docker variants and a check that the data itself comes back (`../todo.md`).
- **Each app has its own `HOME` and `TMPDIR`** (2026-09-30) for everything that runs its code. Build steps keep the server's `HOME` until builds stop running as `hop3`.
- **`[env]` is no longer on the `attach-daemon` command line** (2026-09-24): workers source a `0600` file.
- **The capability experiment** (2026-09-24, ADR 055 §4): a `setpriv` wrapper performs the drop; uWSGI ignores `uid`/`gid` unless root and would pass the Emperor's capabilities to every app.
- **rootd refuses callers inside the app runtime** (2026-10-11): a caller in the `uwsgi-hop3` cgroup or `hop3.slice` (systemd), or descended from the Emperor (without systemd, weaker: a double fork escapes it). Fixture `200-flask-rootd-refused`.
- **The catalog is published** with the state fixes (2026-10-13).

### Headline 2: php-fpm (2026-09-11 to 09-30)

The pool runs as a uWSGI `attach-daemon`, nginx speaks FastCGI to it, and the readiness gate probes a backend in its own protocol. All fourteen PHP recipes migrated and passed a full catalog run (2026-09-21). The Nix path uses the same pool, and all eighteen variants pass. The PHP vhost refuses hidden files, and `[proxy] deny` lists a recipe's data paths. It shipped with seven defects no test could see, because every recipe's own `[run].start` overrode the new worker; the rule it produced is in [`../testing/status.md`](../testing/status.md).

### Headline 3: local-source builds (2026-09-16 to 10-05)

`php-app`, `python-venv` and `node-pnpm-install` build from the recipe directory behind a shared source filter. First real builds found three bugs the parse sweep missed. One fixture per template under `apps/test-apps-nix-gen/`, and the tutorial `docs/tutorials/nix/nix-gen-flask.md`.

### Headline 4: in part

A recipe sets its Node version with `[build].node-version`. npm and pnpm are pinned server-wide and reconciled on every install (2026-09-14, 10-06). `--with rust|clojure|elixir` installs those toolchains on request (2026-10-05). The rest moved to 0.9 on 2026-10-19.

### Roles and the sign-in gate (2026-09-25)

The control plane has four fixed roles (ADR 061). The access gate works on nginx, Caddy and Traefik (ADR 062), with login CSRF. Caddy and Traefik serve apps for the first time, each with its e2e. Both ADRs are accepted.

### Email harness (2026-10-04)

`--with email` installs Mailpit, the `catch` backend captures, `hop3 server email caught` reads it back, and fixture `190-flask-email` checks the path.

### The command surface: target and transport (ADR 042, fourth revision)

Every target is a named context. HTTPS is the everyday transport, with SSH for bootstrap and rescue. The login surface names one axis. The HTTPS path against a real domain is still owed (Before tagging).

### Catalog presentation (0.7.2)

One entry per application with the other build paths on its page, recorded in ADR 059; `index.json` unchanged.

### Work the plan did not list

- **The installer fails loud** ([`../installer-fail-loud-audit.md`](../installer-fail-loud-audit.md)): about 74 of 105 warning sites now stop the install. A deploy past an unlisted ⚠ fails its test run.
- **A review of everything since 0.7** found 42 problems, five serious; all fixed with regression tests.
- **The executable tutorials pass again** after failing unnoticed on Docker from June to October.
- **An update reaches existing servers**: `hop3-deploy-server --reconcile` applies the platform's settings without restarting apps.
- **Remote `check.py` runs for apps without credentials** (2026-10-12): they had failed with exit 2 on a missing file since July.
