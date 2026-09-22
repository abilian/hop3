# Plan: 0.8: the platform underneath the apps

**Created:** 2026-08-01. **Owner:** SF. **Target:** September 2026.
**Predecessor:** [`plan-0.7.x.md`](plan-0.7.x.md): fixes and polish on what 0.7 ships. Anything that repairs 0.7 belongs there; this file is for what 0.8 *adds*.
**Successor:** [`plan-0.9-plus.md`](plan-0.9-plus.md) (the queue behind this release) and [`parked.md`](parked.md) (directions not scheduled).
**Sources:** the "After 0.7" list in [`../todo.md`](../todo.md), TR-03 §9 (Future Work), the draft and deferred ADRs, the per-app experience reports and their deferral records, the team's internal roadmap notes.

## The theme

0.7 answered a question about applications: *do real self-hosted apps deploy on Hop3 and actually work?* Twenty of them do, verified by signing in. The same campaign produced a long list of things the *substrate* cannot yet express or protect, and almost every item below was found by an application running into it.

**0.8 is about the platform underneath the apps.** Three properties it does not have today:

1. **Apps are not isolated from each other or from the control plane.** Every native app runs as the `hop3` user, so any app can reach the privileged helper's socket and pass its credential check, read every other app's environment and addon credentials, and interfere with a sibling's resources. This is the single largest correctness gap in the platform. It is invisible to every test we have because nothing in the corpus is hostile.
2. **The generator only packages software fetched from elsewhere.** Nine of eleven templates build a downloaded artefact. An operator deploying *their own* application, the git-push case the platform otherwise centres on, has no route to the Nix path except a hand-written expression. TR-03 §7.1 states this as a limitation; 0.8 is where it stops being one.
3. **The largest ecosystem in the catalog has no production runtime.** Ten catalog PHP apps serve through a single-threaded development server, which is why an installer could deadlock against its own only worker.

Everything else in this plan is secondary to those three. A release that closes them is a substantially different platform.

A fourth property belongs on that list and is absent on purpose: nothing watches a process that dies (ADR 029), and multi-process applications rely on convention alone (ADR 038). Both are in [`parked.md`](parked.md): they are the most conspicuous gaps this release does *not* close, and each would change the platform's shape.

## The four headline items

### 1. Per-app UID separation (ADR 055)

**The problem.** Every native app runs as `hop3`. Three consequences follow, and the first is a live escalation path:

- Any app can `connect()` to `/run/hop3-rootd/socket` and pass the `SO_PEERCRED` check, because the credential the helper validates is the one every app already has. Untrusted application code reaches root **without compromising anything**: no exploit is required.
- `app_name` is caller-asserted with no ownership binding, so app A can `cgroup.remove(app_name="victim")`, OOM-strangle a sibling, close its ports, unmount its volume, or repoint its outbound mail.
- `/home/hop3/hop3.db`, every app's `[env]`, and all addon credentials are readable by any app.

**The shape** (from ADR 055, Proposed 2026-07-08): per-app `hop3-app-<name>` users, a capability-scoped uWSGI Emperor (`AmbientCapabilities=CAP_SETUID CAP_SETGID`), per-app filesystem ownership, user deletion on destroy, and a migration for existing apps.

**Do the smaller increment first.** ADR 055 names a **shared `hop3-apps` user** as an acceptable first step: it closes the rootd hole and the control-plane secret exposure without solving inter-app interference. That is a much smaller change with most of the security value, and it can ship while the per-app work is still in design. Recommended sequencing: the shared app user ships in 0.8; per-app UIDs come behind it.

**Open questions to settle first** (seven in the ADR; these three gate implementation): UID/GID allocation and reuse safety after destroy; whether the minimal capability set actually covers what uWSGI needs, which wants a small experiment and has a root-Emperor fallback; and POSIX groups versus ACLs for read-down access and addon Unix sockets. Replacing the Emperor (ADR 023) changes the mechanism this rests on.

- [ ] Run the capability experiment; record the result in the ADR.
- [ ] Ship the shared `hop3-apps` user with a migration.
- [ ] Move ADR 055 from Proposed to Accepted with the increment recorded.

### 2. PHP-FPM: a production runtime for ten catalog apps

Ten of the twenty catalog applications (BookStack, Dolibarr, Easy!Appointments, Invoice Ninja, Kanboard, LimeSurvey, Matomo, Nextcloud, Paheko, WordPress) serve through PHP's built-in single-threaded server or `artisan serve`. Requests serialize, and Nextcloud and Matomo issue concurrent internal sub-requests, which is how the installer deadlocked against its own only worker during the verification campaign. 0.7 worked around it by raising the worker count; the fix is a real runtime. **0.7.2 moved the workaround into the generator** (`PHP_CLI_SERVER_WORKERS` is set for every recipe served by the built-in server or `artisan serve`), so it now travels with the template instead of being remembered per recipe. It is still a workaround: requests still serialize per worker.

**The runtime landed 2026-09-11 and the recipes moved onto it 2026-09-16.** php-fpm runs as a uWSGI `attach-daemon`, so the Emperor stays the only process manager and ADR 023 is untouched; nginx speaks FastCGI to the pool and serves the front-controller directory; the readiness gate learned that some backends do not speak HTTP (`notes/readiness-and-non-http-backends.md`).

**Serve PHP through php-fpm behind the reverse proxy.** One platform fix, fourteen applications, and it converts the largest ecosystem in the catalog from "works in a demo" to "works under load". This is the release's highest value-per-unit-work item.

**What the migration cost.** The worker-precedence rule (`core/manifest.py:119-124`) reverts `backend_protocol` to `http` whenever a recipe declares its own `web` worker, and every PHP recipe declared `[run].start`. The runtime therefore shipped with a green unit suite and seven defects that no test could see, because nothing had taken the path. The pool never started: `exec` truncated its command at the `&&`. Static assets returned 403 from a `0o700` mask the static deployer shared. php-fpm cleared the worker environment, so no addon credential reached a PHP app. `[healthcheck].contains` went unevaluated for a FastCGI backend, silently weakening the gate for the six recipes whose marker distinguishes an installed app from an install wizard. The failure diagnosis probed a port that speaks no HTTP. The harness reported every serving PHP app as crashed. And `[build].document-root`, the documented escape hatch, read a file nothing writes.

The rule it produced is recorded in [`../testing/status.md`](../testing/status.md): when a precedence rule lets existing configuration override a new code path, that path has no users on the day it ships, so its fixture has to exist before it does.

- [x] php-fpm pool per app, wired to the existing proxy plugins. Shipped 2026-09-11: the pool runs as a uWSGI `attach-daemon`, nginx speaks FastCGI to it, and the readiness gate learned to probe a backend in its own protocol.
- [x] Migration for the deployed recipes; the recipes got simpler. All fourteen migrated 2026-09-16, and all fourteen passed a full catalog run against the fixed server on 2026-09-21 (the ten golden ones in run 1176, the four alpha ones in run 1174). Two recipes also shed a workaround whose reason was the development server (wordpress's `DISABLE_WP_CRON`, monica's skipped `config:cache`), and kanboard's database configuration turned out to have been dead since it was written. mediawiki's tarball truncation came from a poisoned entry in the Docker download cache; it passes on a remote target.
- [ ] **The Nix `php_app` template still emits `php -S`** (`plugins/build/nix/gen/templates/php_app.py`), so invoice-ninja-nix, invoice-ninja-nixgen and nextcloud-nixgen keep the runtime the native path just replaced. Same defect, other builder.
- [ ] Two hardening items the migration surfaced and did not cause, recorded in the internal blocker list: one recipe writes a config file into the served tree, and four keep application data inside the document root behind an `.htaccess` nginx ignores. The platform question under both is whether the generated PHP vhost should carry a deny list, and where a recipe would declare one. That belongs with the "a recipe cannot influence its own vhost" work.

### 3. Local-source builds: give the generator the git-push case

Nine of the eleven templates package *fetched* software (a release tarball, a registry package, a nixpkgs attribute, an upstream binary) because the evaluation corpus was made of exactly that. `go-source` and `ruby-bundler` are the exceptions, and both used a bare `./.` with no source filter. An operator deploying their own code has no nix-gen route at all.

The change is mechanical: `src = ./.` builds from the recipe directory. The reproducibility argument is untouched, since the dependency-pinning machinery is unchanged either way.

**A source filter had to ship first.** A repo-wide grep for `cleanSource|filterSource|gitignoreSource` returns zero hits. The builder also sets the worker's working directory to the source path, so everything an app writes at runtime (generated config, `.env`, a SQLite database, the writable-tree copy) accumulates *inside the future `src`*. A second build of unchanged code would be a different derivation, and runtime secrets would land in a world-readable store. A shared `lib.cleanSourceWith` shipped first; the two templates that already had local source (`go-source`, `ruby-bundler`) moved onto it in the same change.

- [x] Extend `php-app`, `python-venv` and `node-pnpm-install` to build from the recipe directory (2026-09-16). Local source is an explicit flag per template (`pip-local-source`, `node-local-source`). A first cut inferred it from a missing `url`, which regenerated three fetch-based recipes as local-source apps. `php-app` refuses composer and `needs-writable-dir` with a diagnosis: the first would pin a hash of the app author's own lockfile, and the second copies the store tree back over the directory it was just read from.
- [ ] **Verified only by parse so far.** `nix-instantiate --parse` over the corpus is what the unit sweep runs; no local-source expression has been *built*.
- [ ] One fixture per template under `apps/test-apps-nix-gen/`, `[test].covers` including `nix`. Two of the three need a dependency hash read off a failed Nix build; the `php-app` fixture waits on the template's `php -S` (headline 2).
- [ ] A tutorial that takes a first-party application from `git push` to a hermetic Nix deploy: the story the platform has never been able to tell. It goes beside `docs/tutorials/nix/nix-flask.md`, which teaches the same app through a hand-written `hop3.nix`, so the pair reads as a before and after. **This is the point of the item**, and it is what remains.

### 4. Installer composability: toolchain versions as a choice

The server ships one Node version (18.19.1) and no pnpm, so umami (needs ≥20) and ghost (needs pinned ≥18.12) cannot be packaged natively, and native Outline and Strapi are blocked by the same wall. This was ranked third in DEFERRED-APPS' own "most useful next steps".

- [ ] `hop3-install server --with=rust|nodejs-18|nodejs-22|pnpm|headless-browsers|latex`, composing with the existing `--with` features.
- [x] Per-app `[build].node-version` so a recipe declares what it needs. The Node toolchain installs the pinned version into the app's venv via `nodeenv --prebuilt`, and aborts naming the recipe's own value when `nodeenv` is missing.
- [ ] **The package manager has no equivalent, and that is the live half now.** A recipe pins its Node and then gets whichever pnpm is current. Etherpad has absorbed three breaking pnpm-10 changes in its download script to compensate; the third, upstream's plugin migration calling `pnpm ls --no-production` (a flag pnpm 10 removed), is a fatal startup error, so it presents as an app that will not boot even though the build succeeds. Blocker #33 asks *which* package manager (dispatch from the lockfile); this asks *which version*, and the two want deciding together.
- [ ] Set kernel sysctls the platform requires (`vm.max_map_count` for bundled Elasticsearch): PaaS-level configuration that unblocks SonarQube and anything Elasticsearch-shaped.

## Second tier: smaller in consequence

### Email: make the built things real

The ADR 054 model is settled and 0.7 shipped the interface; 0.8 is validation and wiring.

- [ ] **Unblock the test harness first.** `hop3-test` maps every `[[addons]]` type to a `--with` feature, so `type = "email"` aborts `validate_features`, which means *the email dimension is untestable end to end*. Provision a catch backend post-install using the bootstrap in `tests/c_e2e/test_email_catch.py` and route `email` out of `catalog/features.py`. Everything else here depends on it.
- [ ] **Direct backend from preview to supported**: an e2e against pebble or a local DNS/MX rig (never a real provider quota), opendkim under a process manager on the non-systemd path, DKIM rotation and DNS cutover.
- [ ] **Per-app override via the loopback**: the rootd sender-map operations already exist and are dormant; this is the wiring (`sender_dependent_relayhost_maps`, rebuilt from the DB at the deploy boundary).
- [ ] **Catalog rollout tail** (~15 apps): Django/Flask/generic read env directly and are nearly free; Dolibarr, Easy!Appointments, Keycloak, Kanboard, Nextcloud and Paheko store SMTP in a database or config file, so the mapping goes in their setup step.

### Control-plane audit log

ADR 010 states the gap: rootd has an audit log, the control plane has none for RPC-level security events. Already scheduled for 0.8 in the security remediation plan. Modest work, and it is what makes an incident reconstructible.

### Monitoring and resource metrics

The work covers cgroup v2 per-app tracking, CPU/memory/disk collection, a Prometheus-format `/metrics` endpoint, and a dashboard widget. Long planned and never started. It is also the **blocker for email outage/health notifications**, and the substrate a "threat dashboard" (`../todo.md`) would render.

### Finish the command surface (ADR 047 + a command-manifest ADR)

TR-03 §9.5 calls this the substantive open item in the CLI: the resolution chain is hard to reason about, several concepts are reachable under more than one spelling, and the governing records are still drafts. ADR 047 would make the resolved application and environment travel with each invocation so the server sees a decided context.

This is a **breaking change** requiring one coordinated CLI+server release: an unknown `extra_args` key reaches the command as a kwarg and raises `TypeError`, so mixed old-server/new-client is unsupported. The complementary command-manifest ADR (which would also absorb `DESTRUCTIVE_COMMANDS` and `_MISMATCH_GUARDED_PREFIXES`, the two sibling hardcoded lists with the same disease) is unwritten and should precede the work.

**The target and transport half is done** ([ADR 042](../adrs/042-cli-context-model.md), fourth revision). It was the part of "hard to reason about" that could be settled without the breaking change, and it removes three of the disagreements ADR 047 would otherwise inherit:

- **Every target is a named context.** No unnamed default target resolving below every context (and so silently ignored); one key for which context is current, not two read by two functions that disagreed; `default` and `env` reserved, the latter giving the environment's own `HOP3_API_URL` a name in the model instead of leaving it an invisible override. A one-shot migration converts existing configurations and aborts on the one ambiguous shape.
- **HTTPS is the everyday transport; SSH is bootstrap and rescue.** A login asks the server for its public address and records that, keeping the SSH target only to mint tokens. Routine read-only work stops running through a root shell. ADR 014's "SSH access is authentication" had been read as forbidding this reduction, when it was a claim about authority, and one about transport was never made. A server with no admin domain keeps the tunnel and says so, so the admin domain actually gates something.
- **The login surface names one axis**, which client receives a credential, instead of one flag naming a transport and its apparent sibling naming a destination.

What that leaves for ADR 047 and the manifest: the *app* resolution chain and its conditional trust, the resolved context travelling to the server, and the two hardcoded command lists. The context model underneath them is now one thing.

Not yet proven: the HTTPS path has only been exercised against a server with an admin domain in unit tests. The Docker e2e target has neither a domain nor a trusted certificate, so it covers the SSH fallback and the server-side probe. One run against a real domain is owed before the change is advertised.

### Catalog: one core behind two front-ends

0.7.x gave the catalog a public site (`apps.hop3.cloud`) that shares hop3-server's loader and taxonomy by importing them. That sharing works and is the right shape; what it lacks is a home. `packages/hop3-marketplace` depending on the whole of `hop3-server` (Litestar, SQLAlchemy, the plugin manager) to render static HTML is a dependency direction no one would choose.

- [ ] Extract `hop3-catalog-core`: models, loader, taxonomy, policy, and the view-model both renderers consume. Pure Python, no web framework. `hop3-server` keeps everything about fetching, verifying and installing: that is trust and state, and the other package is presentation.
- [x] **Settled in 0.7.2, and it did not have to change `index.json`.** The catalog shows one entry per application, with the other build paths offered on its page. The fields marking a variant travel in each app's own `catalog.toml`, already inside the flat per-app tree, so the artefact shape deployed servers consume is unchanged and the ADR 049 question never had to be opened; the decision is recorded in [ADR 059](../adrs/059-catalog-maturity-status.md) instead, which owns an application's identity. For 0.8 this leaves the extraction below.

### Catalog growth

- [ ] More applications, now that the packaging playbook and the verification bar exist.
- [ ] `nixpkgs-wrapper` supporting sibling packages (`nixpkgs-packages = {main = "…", assets = "…"}`): unblocks Vaultwarden, WriteFreely and GoToSocial, and is the companion-archive hook that Outline, PeerTube, Funkwhale and Chatwoot will also need.
- [ ] Node/pnpm workspace layouts (ESM/CJS mismatch, dangling virtual-store symlinks): blocks Directus, HedgeDoc, and future Outline/Strapi/Rocket.Chat.

## After 0.8

The queue behind this release is [`plan-0.9-plus.md`](plan-0.9-plus.md): the second UID-separation increment, SSO and MFA, the isolation ADR and the alternative backends behind it, the runtime-stack replacement (ADR 023), deployment strategies, backups phases 2 and 3, supply-chain attestation, and a tail of smaller self-contained items.

Directions *not* scheduled (the agent model, multi-component applications, the generator's second output target, the classifier extraction, and portability as a nightly property) are in [`parked.md`](parked.md), with the reason each is held back.

## What would make 0.8 a good release

If the four headline items land, the platform is one an operator can be handed without a list of caveats. An app that cannot reach root or read its neighbour's secrets. PHP served properly. A generator that packages your own code. An installer that can be asked for the toolchain you need. That is the bar.

The second tier is where scope should be cut first if September gets tight, with one exception: **the email test-harness unblock is small and gates a whole dimension of testing**, so it should survive any cut.
