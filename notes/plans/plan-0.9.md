# Plan: 0.9: one Unix user per app

**Created:** 2026-11-01. **Owner:** SF. **Target:** no fixed date; the release follows the checks in [Before tagging](#before-tagging).
**Predecessor:** [`plan-0.8.md`](plan-0.8.md): 0.8.0 tagged 2026-10-27, 0.8.1 tagged 2026-11-01. Fixes to 0.8 go under its 0.8.x section.
**Work plan for the headline:** [`plan-0.9-per-app-users.md`](plan-0.9-per-app-users.md). **Design record:** [ADR 055](../adrs/055-app-runtime-uid-separation.md) (Proposed).
**Queue behind it:** [`plan-0.9-plus.md`](plan-0.9-plus.md), and [`parked.md`](parked.md) for directions not scheduled.

This file reads in time order: the decisions the work rests on, the work in order, then the checks before tagging.

## The theme

0.8 shipped with one caveat, stated in the release notes: all native apps run as `hop3`, the control plane's user. Any app can read `hop3.db`, the other apps' environments and all addon credentials, and can signal its neighbours. rootd's caller check (0.8) stops app code reaching root. It does nothing for the rest.

**0.9 removes that caveat.** Each app runs as a Unix user of its own, at build time too: a step that executes recipe code runs as the app's user. The app's code and venv are read-only to it. A switch of user goes through hop3-rootd; no sudo, in any form.

**What makes 0.9 a good release:**

- The caveat is gone from the release notes. A fixture proves it in each run: an app cannot read `hop3.db` or a sibling's environment file, and cannot call rootd.
- An upgrade from 0.8.x moves the installed apps to their users with no operator action beyond running the update. Each app restarts once. The update says so.
- The catalog passes on 0.9 as it passes on 0.8: blank-slate, published, and after the upgrade.

The headline changes the owner of the files under `apps/`, the user of the app processes and the user of the toolchains' builds. It touches all recipes. That is the argument for keeping the rest of the release small (decision 1).

## Status, 2026-11-01

- **Headline:** designed, nothing built. The work plan (2026-10-09, moved to 0.9 with build-time isolation on 2026-10-11) holds the design, the new rootd operations, the call sites and the order of work.
- **What 0.8 already delivered for it:** state out of `src/` (`scratch` volumes, volumes linked after the build, a harness that fails an app writing into `src/`); a per-app `HOME` and `TMPDIR` for run-time commands; `[env]` off the `attach-daemon` command line; the capability experiment that settled the Emperor's drop (`setpriv` wrapper, ADR 055 §4); rootd refusing callers inside the app runtime; rootd itself running from a root-owned venv in `/opt/hop3-rootd` (0.8.1).
- **Scope beyond the headline:** undecided (decision 1).

## Decisions needed before code

### 1. What else 0.9 takes

The two rounds cut from 0.8 ([`plan-0.9-plus.md`](plan-0.9-plus.md#cut-from-08-2026-10-13)) were filed as first in the queue. They fall in three groups:

- **Brought by the headline**, so not optional: listed under [Work the headline brings with it](#work-the-headline-brings-with-it).
- **Small and due:**
  - refuse the literal `hop3 login --token <token>` (0.8.1 warns, which was the release the deprecation waited for);
  - the control-plane audit log (ADR 010), modest work that makes an incident between apps reconstructible.
- **Independent of the headline, though each changes the server:** email beyond the harness, monitoring and metrics, the command surface (ADR 047 and the command-manifest ADR), the `hop3-catalog-core` extraction, installer composability (`--with nodejs-*`, the pnpm experiment, kernel sysctls), Caddy and Traefik in the installer, per-app roles, and recipe upgrades for installed catalog apps.

**Recommendation:** the headline, what it brings with it, and the two small items. The third group stays in the queue. An item from it moves in only if it touches neither the build path nor the run path.

- **What it buys:** the blank-slate, published and upgrade runs each test one large change, so a failure points at it.
- **What it costs:** recipe upgrades wait another release, so a catalog fix still reaches new installs only.
- **What decides:** whether a catalog security fix has to reach installed apps before 0.9 can ship. If one does, recipe upgrades move in, with the short ADR they need.

### 2. Nix: single-user or multi-user

The installer sets up Nix single-user, with the store owned by `hop3` and `sandbox = relaxed`, so all Nix derivations build as `hop3`. An app's user cannot write that store, so moving builds to the app's user does not reach Nix as it stands.

- **Multi-user (the `nix-daemon` with `nixbld` build users).**
  - *Buys:* derivations build as `nixbld` inside the sandbox for all Nix apps at once. The app's user only asks the daemon for a build.
  - *Costs:* an installer change, a migration of existing stores on upgrade, and a re-check of the recipes that rely on `__noChroot` under `sandbox = relaxed`, across the 68 Nix recipes.
- **Single-user kept.**
  - *Buys:* no change to the Nix install.
  - *Costs:* Nix builds stay as `hop3`, which the release notes would have to state as the remaining caveat.

**What decides:** whether 0.9 may ship with Nix builds as the stated exception. The work plan settles this before writing code.

### 3. UID allocation and reuse (ADR 055, open question 1)

The work plan proposes `useradd --system` and records app → (user, uid) in rootd's state. Teardown kills the app's processes and removes the app's tree before `userdel`, so no file of a deleted uid is left in `apps/`.

- **`useradd --system`.**
  - *Buys:* nothing to maintain.
  - *Costs:* the system range (100 to 999 by default on Debian and Ubuntu) is shared with distribution packages. A freed uid is reused.
- **A reserved range, allocated by rootd.**
  - *Buys:* a capacity we choose, and uids recognisable as apps.
  - *Costs:* rootd needs an allocator. The range must not collide with what the distribution allocates.

**What decides:** how many apps one server must hold. Cross-instance restore (since 0.5) adds a constraint either way: an archive records numeric owners, so a restore re-owns the files to the target app's user (below).

### 4. How the control plane reads `data/` (ADR 055, open question 3)

`data/`, the volumes and `home/` become `0700`, owned by the app. The work plan answers the question by running backup and restore as the app's user through `as_app`. It still needs agreeing, and recording in the ADR, with the volumes' mountpoint ownership (open question 4).

ADR 055 moves from Proposed to Accepted once decisions 2 to 4 are recorded in it.

## Work, in order

1. **The decisions above**, written into ADR 055.
2. **The headline**, in the work plan's order, each step tested before the next ([`plan-0.9-per-app-users.md`](plan-0.9-per-app-users.md#order-of-work)):
   1. rootd's `app_user` and `app_process` operations;
   2. rootd's `app_exec.spawn`, which passes descriptors back;
   3. the installer gains the vassal wrapper, the Emperor's capabilities under systemd and under supervisor, the user map and `hop3-server apps:separate`;
   4. hop3-server: `as_app` and each run-time call site, the vassal install, the reaper, the deploy's uid check, destroy;
   5. builds as the app's user;
   6. go or no-go on Docker, in a branch that can be dropped whole.
3. **Work the headline brings with it** (below), alongside the step it belongs to.
4. **The small items**, if decision 1 takes them.

### Work the headline brings with it

Each of these breaks, or changes meaning, once apps run as separate users with `src/` and `venv/` read-only. Most come from the 2026-09-28 survey of where apps write ([`../todo.md`](../todo.md), Packaging).

- **uv installs without bytecode.** The Python toolchain's `uv sync` has no `--compile-bytecode`, so a uv-built app compiles into the venv at run time. A read-only venv stops that without an error. Each start then pays for it. Compile at build time.
- **A PHP document root is made world-readable** (`run/served_tree.py`, `a+rX`), so any local user can read WordPress's `wp-config.php` and the database password in it. The work plan's seal keeps `a+rX` on served trees. Once php-fpm runs as the app's user, nginx needs the static files only. Decide the served-tree rule in the seal step.
- **Build steps that write fixed names in `/tmp`** (sonarqube's `/tmp/sonarqube.zip`) collide in the sticky `/tmp` once two users run them. Builds get the app's `TMPDIR` when they move to the app's user.
- **Build caches in the control plane's home** (`~/.cargo`, `~/go`, `~/.npm`, the pnpm store) move to the app's `home/`, which also stops one app's build poisoning another's.
- **Build hooks inherit hop3-server's whole environment**, `HOP3_SECRET_KEY` included. They get `build_app_env`, as the run-time commands do.
- **Apps that write into their code at run time** fail once `src/` is read-only. 0.8's harness catches them on the native and Nix variants. The Docker variants are not checked. Nextcloud's app-store apps land in `apps/` beside the bundled ones (upstream's answer is a writable `custom_apps/` on a volume).
- **Volumes provisioned by rootd** (`bind`, `tmpfs`) are mounted owned by the app's user.
- **A restore re-owns what it unpacks** to the target app's user, since a cross-instance archive records the source server's uids.
- **The isolation fixture.** The work plan names it `200-flask-isolation`, which collides with the existing `200-flask-rootd-refused`. Extend that fixture with the read checks, or take a free number.

## Before tagging

0.8's gate taught three things. The "catalog run" it recorded twice was the nine-fixture smoke profile, because `run` without `--mode` selects `smoke`. The HTTPS login path was owed for two revisions of ADR 042. The protected-server run happened only after the tag, as a Docker e2e (2026-10-31). Each check below names the command and what finishes it.

- [ ] **The isolation fixture** passes beside a second app, on Docker and on a systemd server: the app sees the uid it was given, rootd refuses it, and it cannot read `hop3.db` or the sibling's `worker-env/*.env`.
- [ ] **The upgrade path.** The upgrade chain (`hop3-test upgrade-chain`, run from 0.7.5 on Docker since 2026-10-31) from 0.8.1 with the golden set deployed: the update's reconcile runs `apps:separate`, each app restarts once, runs as its user, and passes the validations, data included.
- [ ] **Destroy** removes the user, the processes and the files of the deleted uid.
- [ ] **A full catalog run on a blank-slate server:** `uv run hop3-test run --provider hetzner --host <throwaway box> --with all --from local --mode full`. Finished when the golden, beta and alpha tiers pass on the rebuilt box with an empty Nix store. Last done on 2026-09-21.
- [ ] **The published catalog:** `uv run --with playwright hop3-test run --host <server> --recipes published --with all --screenshots`, after the upgrade and on a fresh install.
- [ ] **The tutorial suite on a remote server:** `uv run hop3-test run --host <server> --from local docs/tutorials`.
- [ ] **`make test-e2e` on a quiet machine**, (one e2e session per machine).
- [ ] **The HTTPS login path against a real admin domain** with a trusted certificate, then `180-flask-gated`, which the runner includes only on such a server. Owed since 0.8; the Docker e2e covers a pinned certificate only.
- [ ] **Release notes:** the caveat removed from "Upgrading", the restart per app stated, the notes in `docs/src/reference/release-notes/0.9.md` and the summary in `CHANGES.md`, both dated (`scripts/release.py` refuses otherwise).

## Decided

- **Per-app users and build-time isolation are 0.9's headline** (SF, 2026-10-11). Doing the runtime alone would leave build-time recipe code running as `hop3` and change the ownership of all app files twice.
- **A switch of user always goes through hop3-rootd. No sudo, in any form** (SF, week of 2026-10-05). The uWSGI Emperor is the one exception, settled by experiment: it holds `CAP_SETUID` and `CAP_SETGID` and drops through a root-owned `setpriv` wrapper (ADR 055 §4).
