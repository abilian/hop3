# Plan: 0.8: the platform underneath the apps

**Created:** 2026-08-01. **Owner:** SF. **Target:** the week of 2026-09-28 (set 2026-09-24; was September 2026).
**Predecessor:** [`plan-0.7.x.md`](plan-0.7.x.md): fixes and polish on what 0.7 ships. Anything that repairs 0.7 belongs there; this file is for what 0.8 *adds*.
**Successor:** [`plan-0.9-plus.md`](plan-0.9-plus.md) (the queue behind this release) and [`parked.md`](parked.md) (directions not scheduled).
**Sources:** the "After 0.7" list in [`../todo.md`](../todo.md), TR-03 §9 (Future Work), the draft and deferred ADRs, the per-app experience reports and their deferral records, the team's internal roadmap notes.

## Status, 2026-10-07

The target week has passed. Where each part stands:

- **Headline 1, per-app UID separation:** two of its three steps are done (state survives a redeploy for every native and Nix recipe; each app has its own `HOME` and `TMPDIR`). The third, per-app users, is not started, and ADR 055 is still Proposed. This is the release's open question (see [To release 0.8](#to-release-08)).
- **Headline 2, php-fpm:** done, native and Nix.
- **Headline 3, local-source builds:** done: one fixture per template, built and served, and the git-push-to-Nix tutorial.
- **Headline 4, installer composability:** partly. Rust, Clojure and Elixir are `--with` features; npm and pnpm are pinned server-wide; Node versions per app exist. The per-app package manager and the `--with nodejs-*` family are open.
- **Roles and the sign-in gate:** done (ADR 061, ADR 062, three proxies).
- **Email:** the test harness unblock is done (Mailpit behind `catch`, an end-to-end fixture); direct delivery, the per-app override and the catalog rollout are open.

Work the plan did not list, done in the same cycle:

- **The installer fails loud.** An audit found 105 warning sites, about 74 of which should have stopped the install ([`../installer-fail-loud-audit.md`](../installer-fail-loud-audit.md)); they do, and a deploy that carries past an unlisted ⚠ fails its test run.
- **A review of everything since 0.7** (`devel` against `main`, 76 commits) found 42 problems, five of them serious, and all are fixed: among them a harness that left admin accounts with published passwords on test servers, a gated app's include file that could forward a forged identity header, database passwords on command lines, and production code that changed behaviour under pytest.
- **The executable tutorials pass again.** They could not pass on the Docker target from June to October, and nothing said so (`lessons-learned/e2e-test-infrastructure.md`); 28 of 35 then passed on a remote server, and the seven failures became five platform and tutorial fixes.
- **An update reaches existing servers.** `hop3-deploy-server` on an existing server now applies the platform's own settings (`--reconcile`) without restarting the apps.

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

**The shape** (from ADR 055, Proposed 2026-07-08): per-app `hop3-app-<name>` users, a capability-scoped uWSGI Emperor (`AmbientCapabilities=CAP_SETUID CAP_SETGID`) whose vassals start through a `setpriv` wrapper that does the drop, per-app filesystem ownership, user deletion on destroy, and a migration for existing apps.

**The smaller increment, undecided.** ADR 055 names a **shared `hop3-apps` user** as an acceptable first step. What it buys: it closes the rootd hole and the control-plane secret exposure, with most of the security value. What it costs: every app still reads every other app's data, which is what an operator stands to lose, and its group-writable file model is the part per-app users would replace. What decides: whether per-app users fit in 0.8, now that state is out of `src/` for every native and Nix recipe (step 1 below); the shared user is the fallback if they do not.

**The capability experiment ran on 2026-09-24** (`scripts/emperor-caps-probe.py`, results in ADR 055 §4). The Emperor needs `CAP_SETUID` and `CAP_SETGID`, but uWSGI cannot be trusted with the drop: it ignores `uid`/`gid` unless it runs as root, silently, and passes the Emperor's capabilities to every app, which could then `setuid(0)`. A `setpriv` wrapper does the drop instead and leaves apps with no capabilities; reload and removal still work. The same probe settled the log layout and showed that every app's `[env]` is readable by any local user today, because it travels as `export`s on the `attach-daemon` command line (ADR 055 §6).

**Still gating implementation:** UID/GID allocation and reuse safety after destroy; and builds, which run recipe code (hooks, install scripts) as `hop3` and would keep the rootd hole open at build time (ADR 055 open question 6). Replacing the Emperor (ADR 023) changes the mechanism this rests on; the wrapper carries over to any runner that starts a command.

- [x] Run the capability experiment; record the result in the ADR. Done 2026-09-24: a `setpriv` wrapper, not uWSGI, performs the drop.
- [x] Stop delivering `[env]` on the `attach-daemon` command line (ADR 055 §6). Done 2026-09-24: workers source a `0600` file; an app picks it up on its next deploy.
- [ ] Move ADR 055 from Proposed to Accepted with the increment recorded.

**What running an app as another user would break (surveyed 2026-09-28).** A static read of every catalog recipe, asking where each app writes at runtime, changed the order of work:

- **Most stateful apps keep their state in `src/`, which every deploy replaces.** Nine of the twenty golden recipes keep user files or configuration there with no volume (Nextcloud's user files, WordPress's uploads, Mattermost's files among them), 32 of the 34 beta Nix variants, and about 20 of the 29 native alpha apps. A redeploy deletes it. Nothing caught it, because the harness deployed each app once.
- **The same writes are what a read-only `src/` would break.** Once state lives in volumes, what remains is regenerable caches.
- **Per-app users cannot start with the runtime alone.** `before-run`, `[admin].create` and `[probe].create` run as `hop3` and leave files the app must then read and write (configuration written `0600`, SQLite databases, Laravel logs, Nextcloud's `occ` ownership check). They move to the app's user in the same change as the runtime.
- **Every app runs with `HOME=/home/hop3`**, the control plane's home.

The item is now three steps:

- [x] **State survives a redeploy.** Platform, 2026-09-28: `scratch` volumes; volumes linked after the build, a newly declared one seeded from the tree the deploy replaces; a harness that fails an app writing into `src/` and redeploys every app. The first measurement passed 7 of 20 golden recipes; after the fixes, all 20 pass on Docker, redeploy included. 2026-09-29: a Nix wrapper's config files and `pre-exec` run once per deploy as the build's own before-run step, and `writable-home-at-runtime` copies the package at deploy time; all 34 beta Nix variants pass on Docker, redeploy included. The native and Nix alpha recipes too, 54 of 55 (directus-nixgen's dependency hash does not match on arm64). Done for every native and Nix recipe. Not covered: the 52 Docker variants, whose state lives in the container, and a harness check that the data itself survives a redeploy (`notes/todo.md`).
- [ ] **Publish the catalog.** The fixes reach servers only once published, and only new installs then: an installed app has no path to a newer recipe (plan-0.9, recipe upgrades). The 19 published entries that need a 0.8 server now say so with `requires_hop3`.
- [x] **Each app gets its own `HOME` and `TMPDIR`** (2026-09-30), `<app>/home/` and `<app>/tmp/`, for everything that runs the app's code: workers, `before-run`, the `[admin]`/`[probe]` `create` commands (which also stopped inheriting the server's environment), `hop3 run`, `hop3 app shell`. Build steps keep the server's `HOME`, where rustup, cargo, npm and pnpm keep toolchains and caches; they move with step 3, when builds stop running as `hop3` (ADR 055 open question 6).
- [ ] **Per-app users**: hooks and runtime in one change, `src/` read-only to the app.

### 2. PHP-FPM: a production runtime for ten catalog apps

Ten of the twenty catalog applications (BookStack, Dolibarr, Easy!Appointments, Invoice Ninja, Kanboard, LimeSurvey, Matomo, Nextcloud, Paheko, WordPress) serve through PHP's built-in single-threaded server or `artisan serve`. Requests serialize, and Nextcloud and Matomo issue concurrent internal sub-requests, which is how the installer deadlocked against its own only worker during the verification campaign. 0.7 worked around it by raising the worker count; the fix is a real runtime. **0.7.2 moved the workaround into the generator** (`PHP_CLI_SERVER_WORKERS` is set for every recipe served by the built-in server or `artisan serve`), so it now travels with the template instead of being remembered per recipe. It is still a workaround: requests still serialize per worker.

**The runtime landed 2026-09-11 and the recipes moved onto it 2026-09-16.** php-fpm runs as a uWSGI `attach-daemon`, so the Emperor stays the only process manager and ADR 023 is untouched; nginx speaks FastCGI to the pool and serves the front-controller directory; the readiness gate learned that some backends do not speak HTTP (`notes/readiness-and-non-http-backends.md`).

**Serve PHP through php-fpm behind the reverse proxy.** One platform fix, fourteen applications, and it converts the largest ecosystem in the catalog from "works in a demo" to "works under load". This is the release's highest value-per-unit-work item.

**What the migration cost.** The worker-precedence rule (`core/manifest.py:119-124`) reverts `backend_protocol` to `http` whenever a recipe declares its own `web` worker, and every PHP recipe declared `[run].start`. The runtime therefore shipped with a green unit suite and seven defects that no test could see, because nothing had taken the path. The pool never started: `exec` truncated its command at the `&&`. Static assets returned 403 from a `0o700` mask the static deployer shared. php-fpm cleared the worker environment, so no addon credential reached a PHP app. `[healthcheck].contains` went unevaluated for a FastCGI backend, silently weakening the gate for the six recipes whose marker distinguishes an installed app from an install wizard. The failure diagnosis probed a port that speaks no HTTP. The harness reported every serving PHP app as crashed. And `[build].document-root`, the documented escape hatch, read a file nothing writes.

The rule it produced is recorded in [`../testing/status.md`](../testing/status.md): when a precedence rule lets existing configuration override a new code path, that path has no users on the day it ships, so its fixture has to exist before it does.

- [x] php-fpm pool per app, wired to the existing proxy plugins. Shipped 2026-09-11: the pool runs as a uWSGI `attach-daemon`, nginx speaks FastCGI to it, and the readiness gate learned to probe a backend in its own protocol.
- [x] Migration for the deployed recipes; the recipes got simpler. All fourteen migrated 2026-09-16, and all fourteen passed a full catalog run against the fixed server on 2026-09-21 (the ten golden ones in run 1176, the four alpha ones in run 1174). Two recipes also shed a workaround whose reason was the development server (wordpress's `DISABLE_WP_CRON`, monica's skipped `config:cache`), and kanboard's database configuration turned out to have been dead since it was written. mediawiki's tarball truncation came from a poisoned entry in the Docker download cache; it passes on a remote target.
- [x] **The Nix path is served by php-fpm too** (2026-09-30). The `php-app` template emitted `php -S`, and so did the seven hand-written PHP `hop3.nix`: eighteen catalog variants kept the runtime the native path had replaced. A `runtime.json` now asks for the pool with a `php_fpm` entry (the store's binary, the tree, an optional document root), and the Nix builder produces the same pool, worker and FastCGI location as the PHP toolchain, through one helper. `fpm` is the template's default serve mode. All eighteen pass on Docker, redeploy included; nextcloud-nixgen and easy-appointments-nixgen gained the native recipes' `[proxy] deny`, and wordpress-nixgen shed `DISABLE_WP_CRON`.
- [x] **Paths the proxy never answers** (2026-09-25). Four recipes keep application data inside the document root behind an `.htaccess` nginx ignores. The PHP vhost now refuses hidden files (`.env`, `.htaccess`, `.git`) on nginx and Caddy, `/.well-known/` excepted, and `[proxy] deny = ["/data"]` lets a recipe list its own data paths, answered with 404 for any backend; Traefik refuses a deploy that declares one. nextcloud and easy-appointments declare upstream's own rules, piwigo its compiled templates, logs and cache. The fifth item, matomo writing its config without the leading `<?php exit; ?>`, was a recipe line and is fixed.

### 3. Local-source builds: give the generator the git-push case

Nine of the eleven templates package *fetched* software (a release tarball, a registry package, a nixpkgs attribute, an upstream binary) because the evaluation corpus was made of exactly that. `go-source` and `ruby-bundler` are the exceptions, and both used a bare `./.` with no source filter. An operator deploying their own code has no nix-gen route at all.

The change is mechanical: `src = ./.` builds from the recipe directory. The reproducibility argument is untouched, since the dependency-pinning machinery is unchanged either way.

**A source filter had to ship first.** A repo-wide grep for `cleanSource|filterSource|gitignoreSource` returns zero hits. The builder also sets the worker's working directory to the source path, so everything an app writes at runtime (generated config, `.env`, a SQLite database, the writable-tree copy) accumulates *inside the future `src`*. A second build of unchanged code would be a different derivation, and runtime secrets would land in a world-readable store. A shared `lib.cleanSourceWith` shipped first; the two templates that already had local source (`go-source`, `ruby-bundler`) moved onto it in the same change.

- [x] Extend `php-app`, `python-venv` and `node-pnpm-install` to build from the recipe directory (2026-09-16). Local source is an explicit flag per template (`pip-local-source`, `node-local-source`). A first cut inferred it from a missing `url`, which regenerated three fetch-based recipes as local-source apps. `php-app` refuses composer and `needs-writable-dir` with a diagnosis: the first would pin a hash of the app author's own lockfile, and the second copies the store tree back over the directory it was just read from.
- [x] **Built, not only parsed** (2026-10-04). The first builds found three bugs the parse sweep could not, or did not, see: the python-venv wrapper did not parse at all (an unescaped `${PYTHONPATH}`; the sweep had no local Python recipe to run it on), the node install wrote into the read-only copy of the app's tree, and the pnpm store hash changed on every fetch of an unchanged lockfile (pnpm 10 records the build directory's path under `v10/projects`). The last one is what made directus-nixgen's hash "move" between runs.
- [x] One fixture per template under `apps/test-apps-nix-gen/` (2026-10-04): `php-public` (php-fpm from the store, `public/` detected), `python-gunicorn`, `nodejs-express`, beside `golang-minimal`. All four pass on Docker, redeploy included; the pnpm hash recorded on macOS matched on Linux.
- [x] A tutorial that takes a first-party application from `git push` to a hermetic Nix deploy (2026-10-05): `docs/tutorials/nix/nix-gen-flask.md`, beside `nix-flask.md`, the same Flask app with no Nix code. The reader needs no Nix locally; the lockfile is resolved as of a date so its hash is the same for every reader, and MarkupSafe is vendored as source so one hash holds on x86 and ARM. Passes on Docker. Writing it found the executable tutorials unable to pass on Docker since June (`lessons-learned/e2e-test-infrastructure.md`).

### 4. Installer composability: toolchain versions as a choice

The server ships one Node version (18.19.1) and no pnpm, so umami (needs ≥20) and ghost (needs pinned ≥18.12) cannot be packaged natively, and native Outline and Strapi are blocked by the same wall. This was ranked third in DEFERRED-APPS' own "most useful next steps".

- [ ] `hop3-install server --with=nodejs-18|nodejs-22|pnpm|headless-browsers|latex`, composing with the existing `--with` features. `--with rust`, `--with clojure` and `--with elixir` exist (2026-10-05): those toolchains are installed on every server, best-effort, and requesting one makes its failure stop the install.
- [x] Per-app `[build].node-version` so a recipe declares what it needs. The Node toolchain installs the pinned version into the app's venv via `nodeenv --prebuilt`, and aborts naming the recipe's own value when `nodeenv` is missing.
- [ ] **The package manager has no per-app equivalent, and that is the live half now.** The server-wide half is done: the installer pins an exact pnpm and reconciles it on every install (2026-09-14), npm the same way (2026-10-06), and a shadowed copy on PATH stops the install. A recipe still cannot ask for a pnpm other than the server's. Etherpad has absorbed three breaking pnpm-10 changes in its download script to compensate; the third, upstream's plugin migration calling `pnpm ls --no-production` (a flag pnpm 10 removed), is a fatal startup error, so it presents as an app that will not boot even though the build succeeds. Blocker #33 asks *which* package manager (dispatch from the lockfile); this asks *which version*, and the two want deciding together.

  **Experiment before deciding** (SF, 2026-09-25). Three steps, each producing a table:

  1. *Inventory.* For every Node recipe in the catalog, native, Docker and Nix, fetch upstream at the recipe's version and record: the lockfiles present and their `lockfileVersion`, the `packageManager` field of `package.json`, any `engines` entry for npm, pnpm or yarn, and what the recipe does today (an overridden install command, a workaround in a script). This says how many apps name their package manager and its version themselves, and how many ship two lockfiles.
  2. *Native build matrix* on Docker, for the apps with a pnpm or yarn lockfile. Build each three ways: today's server-wide pnpm; the version `packageManager` names, through corepack, installed into the app's venv; and a version installed into the venv beside `[build].node-version`. Record whether it builds, starts and passes `check.py`, the build time, and which of the recipe's workarounds can be deleted (etherpad's three are the test).
  3. *Nix.* `node-pnpm-install` takes its pnpm from the nixpkgs pin, which offers one attribute per major (`pnpm_9`, `pnpm_10`). Build directus-nixgen and etherpad-nixgen with each major and with the major `packageManager` names, and check whether the major is enough for the lockfile.

  What decides: the mechanism that removes the per-recipe workarounds, gives the same answer on both builders (so at most a major on the Nix side, since the sandbox cannot download a pnpm), and fails at build naming the version it could not provide. Corepack downloads the package manager at build time: acceptable on the native builder, not in the Nix sandbox, and that asymmetry is part of what the matrix measures.
- [ ] Set kernel sysctls the platform requires (`vm.max_map_count` for bundled Elasticsearch): PaaS-level configuration that unblocks SonarQube and anything Elasticsearch-shaped.

## Who may reach what: roles and a sign-in gate

Not one of the four headlines when this plan was written, and the largest thing 0.8 adds for an operator. An app was public the moment it deployed, which is right for an application with accounts of its own and wrong for the class people actually deploy: notebooks, admin tools, generated dashboards, staging copies. And any account could run any command, so an account created to let someone into one app could read every app's environment.

- [x] **Standard roles on the control plane** ([ADR 061](../adrs/061-standard-roles-and-rpc-authorization.md), 2026-09-25). Four fixed roles, one per account (`admin > deployer > viewer > member`), checked by the RPC dispatcher and the dashboard on every request and read from the database each time, so a demotion takes effect at once. Default-deny: a command with no declared role is admin-only. New accounts are members and get no token; the migration made existing non-admins deployers. `hop3 user set-role`.
- [x] **Caddy and Traefik serve apps** (2026-09-25). Both existed as plugins and neither had been selected by a test: Caddy failed validation on every deploy, Traefik routed nothing on port 80 and pointed HTTPS at a certificate resolver nothing defined. One e2e per proxy runs the same deploys now. A proxy declares what it can do, and a deploy it cannot serve is refused before the build: FastCGI and files on Traefik, the WAF on both, certbot on both.
- [x] **The access gate** ([ADR 062](../adrs/062-authenticated-access-gate.md), 2026-09-25). `[access] require = "auth"` puts an app behind a Hop3 sign-in, with a minimum role and anonymous public paths, on nginx, Caddy and Traefik. The app is told who is asking in headers a client cannot forge and never sees the gate's cookie. The ADR's eleven acceptance checks run as an e2e on each proxy.
- [x] Move ADR 061 and ADR 062 from Proposed to Accepted (2026-09-25).
- [x] **Login CSRF on the gate** (2026-09-25). The one-time code is bound to a state cookie on the app's host, set when the sign-in starts, so a code works only in the browser that started it. Acceptance item 12, on all three proxies.
- [ ] The gate's remaining open question: bearer tokens for scripts calling a gated API.
- [ ] Caddy and Traefik in the installer: an admin-domain route for each, Traefik's `aliasHeadersStrategy: delete` (the gate relies on it), and certificates made proxy-aware. certbot issuance and renewal are wired to nginx only, so both are refused elsewhere today.
- [ ] Per-app roles, designed into ADR 061 and not built: a deployer reaches every app on the server.

## Second tier: smaller in consequence

### Email: make the built things real

The ADR 054 model is settled and 0.7 shipped the interface; 0.8 is validation and wiring.

- [x] **Unblock the test harness first** (2026-10-04). The `catch` backend relayed to a port nothing in the platform listened on: selecting it succeeded, and every message was deferred, never captured. `--with email` now installs and runs Mailpit (pinned by version and SHA-256, loopback only), selecting `catch` checks it answers, `hop3 server email caught` reads it back, and `hop3-test` selects `catch` for runs that include an email app. The `190-flask-email` fixture sends through the injected relay and finds the message in the sink; the email dimension is testable end to end.
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

## To release 0.8

### The open decision: per-app users in 0.8, or after it

Undecided (SF).

- **Ship per-app users in 0.8.** Buys: the release's first headline in full; the rootd escalation and cross-app reads closed. Costs: the largest piece of work in the plan, still gated on UID allocation and on builds running as `hop3` (ADR 055 open question 6), so the release moves by weeks.
- **Ship the shared `hop3-apps` user in 0.8, per-app users in 0.9.** Buys: the rootd hole and the control-plane secrets closed now. Costs: a group-writable file model that per-app users later replace, and apps still read each other's data.
- **Release 0.8 without either, and make separation 0.9's headline.** Buys: everything else above ships now. Costs: the first property in "The theme" stays open, and the release notes must say so plainly.

What decides: whether UID allocation and build-time isolation can be designed in days. The preparatory steps (state out of `src/`, per-app `HOME`) are done whichever way it goes.

### Before tagging

- [ ] **Publish the catalog** (SF): the state-out-of-`src/` fixes reach servers only from the published catalog, and 19 entries already say `requires_hop3 = "0.8"`.
- [ ] **A full catalog run on a blank-slate remote server**, `--with all`, from the release tree: the gate the advertised set depends on. It is also the only place the Docker-bridge paths (MySQL's Docker user, `pg_hba`, Redis `requirepass`) and the Docker-built variants run.
- [ ] **The full tutorial suite on a remote server**, after the 2026-10-06 fixes (rails, sinatra, jekyll, django, nestjs, nuxtjs, nix-gen-flask were the failures).
- [ ] **`make test-e2e` on a quiet machine** (one e2e session per machine).
- [ ] **Re-record directus-nixgen's `node-deps-hash` on x86_64** (`../todo.md`).
- [ ] **The HTTPS login path against a real admin domain**, owed since ADR 042's fourth revision: only the SSH fallback has run end to end.
- [ ] **Move ADR 055 out of Proposed** with the increment chosen above.
- [ ] **`CHANGES.md` reviewed as release notes**: it has grown by accretion over the cycle.

### The second tier: a proposed cut

Undecided (SF). The second tier was written as "cut first if September gets tight", and September has passed. A proposal, item by item:

| Item | Proposal | Why |
|---|---|---|
| Email: direct backend, per-app override, catalog rollout | 0.9 | The harness unblock, the part that gated testing, is done |
| Control-plane audit log | Keep if small | It makes an incident reconstructible, and it is scoped as modest |
| Monitoring and resource metrics | 0.9 | Long planned, never started, and large |
| Command surface (ADR 047 + manifest) | 0.9 | A breaking CLI and server change; the context model half is done |
| `hop3-catalog-core` extraction | 0.9 | No user-visible effect |
| `nixpkgs-wrapper` sibling packages, pnpm workspaces | 0.9 | Unblock specific apps; catalog growth can follow the release |
| Per-app pnpm, `--with nodejs-*` | Decide with the experiment in headline 4 | The experiment is defined and not run |
| `vm.max_map_count` sysctl | Keep | Small, unblocks SonarQube |
| Gate: bearer tokens for scripts; Caddy and Traefik in the installer; per-app roles | 0.9 | The gate works on nginx for people; these widen it |

## After 0.8

The queue behind this release is [`plan-0.9-plus.md`](plan-0.9-plus.md): recipe upgrades for installed catalog applications, the second UID-separation increment, SSO and MFA, the isolation ADR and the alternative backends behind it, the runtime-stack replacement (ADR 023), deployment strategies, backups phases 2 and 3, supply-chain attestation, and a tail of smaller self-contained items.

Directions *not* scheduled (the agent model, multi-component applications, the generator's second output target, the classifier extraction, and portability as a nightly property) are in [`parked.md`](parked.md), with the reason each is held back.

## What would make 0.8 a good release

If the four headline items land, the platform is one an operator can be handed without a list of caveats. An app that cannot reach root or read its neighbour's secrets. PHP served properly. A generator that packages your own code. An installer that can be asked for the toolchain you need. That is the bar. Roles and the sign-in gate, already in, add the other half: the operator decides who reaches each app.

The second tier is where scope is cut first; the email test-harness unblock, the one item marked as surviving any cut, is done.
