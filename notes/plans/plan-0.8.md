# Plan: 0.8: the platform underneath the apps

**Created:** 2026-08-01. **Owner:** SF. **Target:** September 2026.
**Predecessor:** [`plan-0.7.x.md`](plan-0.7.x.md): fixes and polish on what 0.7 ships. Anything that repairs 0.7 belongs there; this file is for what 0.8 *adds*.
**Successor:** [`plan-0.9-plus.md`](plan-0.9-plus.md) (the queue behind this release) and [`parked.md`](parked.md) (directions deliberately not scheduled).
**Sources:** the "After 0.7" list in [`../todo.md`](../todo.md), TR-03 §9 (Future Work), the draft and deferred ADRs, the per-app experience reports and their deferral records, and the team's internal roadmap notes.

## The theme

0.7 answered a question about applications: *do real self-hosted apps deploy on Hop3 and actually work?* Twenty of them do, verified by signing in. The campaign that established that also produced a long list of things the *substrate* cannot yet express or protect, and almost every item below was found by an application running into it.

**0.8 is about the platform underneath the apps.** Three properties it does not have today:

1. **Apps are not isolated from each other or from the control plane.** Every native app runs as the `hop3` user, so any app can reach the privileged helper's socket and pass its credential check, read every other app's environment and addon credentials, and interfere with a sibling's resources. This is the single largest correctness gap in the platform, and it is invisible to every test we have because nothing in the corpus is hostile.
2. **The generator only packages software fetched from elsewhere.** Ten of eleven templates build a downloaded artefact. An operator deploying *their own* application, the git-push case the platform otherwise centres on, has no route to the Nix path except a hand-written expression. TR-03 §7.1 states this as a limitation; 0.8 is where it stops being one.
3. **The largest ecosystem in the catalog has no production runtime.** Ten catalog PHP apps serve through a single-threaded development server, which is why an installer could deadlock against its own only worker.

Everything else in this plan is secondary to those three. A release that closes them is a substantially different platform.

A fourth property belongs on that list and is deliberately absent: nothing watches a process that dies (ADR 029), and multi-process applications rely on convention alone (ADR 038). Both are in [`parked.md`](parked.md): they are the most conspicuous gaps this release does *not* close, and each would change the platform's shape.

## The four headline items

### 1. Per-app UID separation (ADR 055)

**The problem.** Every native app runs as `hop3`. Three consequences follow, and the first is a live escalation path:

- Any app can `connect()` to `/run/hop3-rootd/socket` and pass the `SO_PEERCRED` check, because the credential the helper validates is the one every app already has. Untrusted application code reaches root **without compromising anything**: no exploit required.
- `app_name` is caller-asserted with no ownership binding, so app A can `cgroup.remove(app_name="victim")`, OOM-strangle a sibling, close its ports, unmount its volume, or repoint its outbound mail.
- `/home/hop3/hop3.db`, every app's `[env]`, and all addon credentials are readable by any app.

**The shape** (from ADR 055, Proposed 2026-07-08): per-app `hop3-app-<name>` users, a capability-scoped uWSGI Emperor (`AmbientCapabilities=CAP_SETUID CAP_SETGID`), per-app filesystem ownership, user deletion on destroy, and a migration for existing apps.

**Do the smaller increment first.** ADR 055 names a **shared `hop3-apps` user** as an acceptable first step: it closes the rootd hole and the control-plane secret exposure without solving inter-app interference. That is a much smaller change with most of the security value, and it can ship while the per-app work is still in design. Recommended sequencing: shared app user in 0.8, per-app UIDs behind it.

**Open questions to settle first** (seven in the ADR; these three gate implementation): UID/GID allocation and reuse safety after destroy; whether the minimal capability set actually covers what uWSGI needs, which wants a small experiment and has a root-Emperor fallback; and POSIX groups versus ACLs for read-down access and addon Unix sockets. Replacing the Emperor (ADR 023) changes the mechanism this rests on.

- [ ] Run the capability experiment; record the result in the ADR.
- [ ] Ship the shared `hop3-apps` user with a migration.
- [ ] Move ADR 055 from Proposed to Accepted with the increment recorded.

### 2. PHP-FPM: a production runtime for ten catalog apps

Ten of the twenty catalog applications (BookStack, Dolibarr, Easy!Appointments, Invoice Ninja, Kanboard, LimeSurvey, Matomo, Nextcloud, Paheko, WordPress) serve through PHP's built-in single-threaded server or `artisan serve`. Requests serialize, and Nextcloud and Matomo issue concurrent internal sub-requests, which is how the installer deadlocked against its own only worker during the verification campaign. 0.7 worked around it by raising the worker count; the fix is a real runtime. **0.7.2 moved the workaround into the generator** (`PHP_CLI_SERVER_WORKERS` is set for every recipe served by the built-in server or `artisan serve`), so it now travels with the template instead of being remembered per recipe. That is still a workaround: requests still serialize per worker, and the item below stands unchanged.

**Serve PHP through php-fpm behind the reverse proxy.** One platform fix, ten applications, and it converts the largest ecosystem in the catalog from "works in a demo" to "works under load". This is the highest value-per-unit-work item in the release.

- [ ] php-fpm pool per app, wired to the existing proxy plugins.
- [ ] Migration for the ten deployed recipes; the recipes should get simpler.

### 3. Local-source builds: give the generator the git-push case

Ten of the eleven templates package *fetched* software (a release tarball, a registry package, a nixpkgs attribute, an upstream binary) because the evaluation corpus was made of exactly that. `go-source` is the exception. An operator deploying their own code has no nix-gen route at all.

The change is mechanical: `src = ./.` builds from the recipe directory. It does not touch the reproducibility argument, since the dependency-pinning machinery is unchanged either way.

- [ ] Extend `php-app`, `python-venv` and `node-pnpm-install` to build from the recipe directory.
- [ ] A tutorial that takes a first-party application from `git push` to a hermetic Nix deploy: the story the platform has been unable to tell.

### 4. Installer composability: toolchain versions as a choice

The server ships one Node version (18.19.1) and no pnpm, so umami (needs ≥20) and ghost (needs pinned ≥18.12) cannot be packaged natively, and native Outline and Strapi are blocked behind the same wall. This was ranked third in DEFERRED-APPS' own "most useful next steps".

- [ ] `hop3-install server --with=rust|nodejs-18|nodejs-22|pnpm|headless-browsers|latex`, composing with the existing `--with` features.
- [ ] Per-app `[build].node-version` so a recipe declares what it needs.
- [ ] Set kernel sysctls the platform requires (`vm.max_map_count` for bundled Elasticsearch): PaaS-level configuration that unblocks SonarQube and anything Elasticsearch-shaped.

## Second tier: worth doing, smaller in consequence

### Email: make the built things real

The ADR 054 model is settled and 0.7 shipped the interface; 0.8 is validation and wiring.

- [ ] **Unblock the test harness first.** `hop3-test` maps every `[[addons]]` type to a `--with` feature, so `type = "email"` aborts `validate_features`, which means *the email dimension is untestable end to end*. Provision a catch backend post-install using the bootstrap in `tests/c_e2e/test_email_catch.py` and route `email` out of `catalog/features.py`. Everything else here depends on it.
- [ ] **Direct backend from preview to supported**: an e2e against pebble or a local DNS/MX rig (never a real provider quota), opendkim under a process manager on the non-systemd path, DKIM rotation and DNS cutover.
- [ ] **Per-app override via the loopback**: the rootd sender-map operations already exist and are dormant; this is the wiring (`sender_dependent_relayhost_maps`, rebuilt from the DB at the deploy seam).
- [ ] **Catalog rollout tail** (~15 apps): Django/Flask/generic read env directly and are nearly free; Dolibarr, Easy!Appointments, Keycloak, Kanboard, Nextcloud and Paheko store SMTP in a database or config file, so the mapping goes in their setup step.

### Control-plane audit log

ADR 010 states the gap: rootd has an audit log, the control plane has none for RPC-level security events. Already scheduled for 0.8 in the security remediation plan. Modest work, and it is what makes an incident reconstructible.

### Monitoring and resource metrics

cgroup v2 per-app tracking, CPU/memory/disk collection, a Prometheus-format `/metrics` endpoint, a dashboard widget. Long planned and never started. It is also the **blocker for email outage/health notifications**, and the substrate a "threat dashboard" (`../todo.md`) would render.

### Finish the command surface (ADR 047 + a command-manifest ADR)

TR-03 §9.5 calls this the substantive open item in the CLI: the resolution chain is hard to reason about, several concepts are reachable under more than one spelling, and the governing records are still drafts. ADR 047 would make the resolved application and environment travel with each invocation so the server sees a decided context.

This is a **breaking change** requiring one coordinated CLI+server release: an unknown `extra_args` key reaches the command as a kwarg and raises `TypeError`, so mixed old-server/new-client is unsupported. The complementary command-manifest ADR (which would also absorb `DESTRUCTIVE_COMMANDS` and `_MISMATCH_GUARDED_PREFIXES`, the two sibling hardcoded lists with the same disease) is unwritten and should precede the work.

### Catalog: one core behind two front-ends

0.7.x gave the catalog a public site (`apps.hop3.cloud`) that shares hop3-server's loader and taxonomy by importing them. That sharing works and is the right shape; what it lacks is a home. `packages/hop3-marketplace` depending on the whole of `hop3-server` (Litestar, SQLAlchemy, the plugin manager) to render static HTML is a dependency direction nobody would choose deliberately.

- [ ] Extract `hop3-catalog-core`: models, loader, taxonomy, policy, and the view-model both renderers consume. Pure Python, no web framework. `hop3-server` keeps everything about fetching, verifying and installing, because that is trust and state rather than presentation.
- [x] **Settled in 0.7.2, and it did not have to change `index.json`.** The catalog shows one entry per application, with the other build paths offered on its page. The fields marking a variant travel in each app's own `catalog.toml`, already inside the flat per-app tree, so the artefact shape deployed servers consume is unchanged and the ADR 049 question never had to be opened; the decision is recorded in [ADR 059](../adrs/059-catalog-maturity-status.md) instead, which owns an application's identity. What this leaves for 0.8 is the extraction below, not the decision.

### Catalog growth

- [ ] More applications, now that the packaging playbook and the verification bar exist.
- [ ] `nixpkgs-wrapper` supporting sibling packages (`nixpkgs-packages = {main = "…", assets = "…"}`): unblocks Vaultwarden, WriteFreely and GoToSocial, and is the companion-archive hook that Outline, PeerTube, Funkwhale and Chatwoot will also need.
- [ ] Node/pnpm workspace layouts (ESM/CJS mismatch, dangling virtual-store symlinks): blocks Directus, HedgeDoc, and future Outline/Strapi/Rocket.Chat.

## After 0.8

The queue behind this release is [`plan-0.9-plus.md`](plan-0.9-plus.md): the second UID-separation increment, SSO and MFA, the isolation ADR and the alternative backends behind it, the runtime-stack replacement (ADR 023), deployment strategies, backups phases 2 and 3, supply-chain attestation, and a tail of smaller self-contained items.

Directions that are deliberately *not* scheduled (the agent model, multi-component applications, the generator's second output target, the classifier extraction, and portability as a nightly property) are in [`parked.md`](parked.md), with the reason each is held back.

## What would make 0.8 a good release

If the four headline items land (an app that cannot reach root or read its neighbour's secrets, PHP served properly, a generator that packages your own code, and an installer that can be asked for the toolchain you need) then the platform is one an operator can be handed without a list of caveats. That is the bar.

The second tier is where scope should be cut first if September gets tight, with one exception: **the email test-harness unblock is small and gates a whole dimension of testing**, so it should survive any cut.
