# Plan: 0.9 and beyond

**Created:** 2026-08-01. **Owner:** SF. **Horizon:** after 0.8 ships, so late 2026 onward.
**Siblings:** [`plan-0.7.x.md`](plan-0.7.x.md) (maintenance), [`plan-0.8.md`](plan-0.8.md), [`parked.md`](parked.md) (not scheduled at all).

## What this file is

This file is the queue behind 0.8. Its work is wanted, has a design or a design record, and has no date. Unlike [`parked.md`](parked.md), nothing here is held back on purpose: these are simply next. Each will move into a release plan when it earns the slot.

Ordered by how likely each is to be picked up first.

## Cut from 0.8 (2026-10-13)

The second tier of [`plan-0.8.md`](plan-0.8.md), moved here by SF so 0.8 can tag on its headlines and its release checks. These are first in the queue.

### Email: make the built things real

The ADR 054 model is settled and 0.7 shipped the interface; the harness unblock is done.

- [ ] **Direct backend from preview to supported**: an e2e against pebble or a local DNS/MX rig (never a real provider quota), opendkim under a process manager on the non-systemd path, DKIM rotation and DNS cutover.
- [ ] **Per-app override via the loopback**: the rootd sender-map operations already exist and are dormant; this is the wiring (`sender_dependent_relayhost_maps`, rebuilt from the DB at the deploy boundary).
- [ ] **Catalog rollout** (~15 apps): Django, Flask and generic apps read the environment directly and are nearly free; Dolibarr, Easy!Appointments, Keycloak, Kanboard, Nextcloud and Paheko store SMTP in a database or config file, so the mapping goes in their setup step.

### Control-plane audit log

- [ ] ADR 010 states the gap: rootd has an audit log, the control plane has none for RPC-level security events. Scheduled for 0.8 in the security remediation plan, and cut from it on 2026-10-13. It is modest work that makes an incident reconstructible.

### Monitoring and resource metrics

- [ ] cgroup v2 per-app tracking, CPU, memory and disk collection, a Prometheus-format `/metrics` endpoint, and a dashboard widget. Long planned and never started. It blocks email outage and health notifications, and is the substrate a "threat dashboard" (`../todo.md`) would render.

### Finish the command surface (ADR 047 + a command-manifest ADR)

TR-03 §9.5 calls this the substantive open item in the CLI: the resolution chain is hard to reason about, several concepts are reachable under more than one spelling, while the governing records are still drafts.

- [ ] **Write the command-manifest ADR first.** It also absorbs `DESTRUCTIVE_COMMANDS` and `_MISMATCH_GUARDED_PREFIXES`, the two sibling hardcoded lists with the same disease.
- [ ] **ADR 047** settles the *app* resolution chain and its conditional trust. The resolved context then travels with each invocation, so the server sees a decided context. A **breaking change** requiring one coordinated CLI and server release: an unknown `extra_args` key reaches the command as a kwarg and raises `TypeError`, so a mixed old-server, new-client pair is unsupported.

The target and transport half is done (ADR 042, fourth revision; see [plan-0.8.md](plan-0.8.md#done)).

### Catalog: one core behind two front-ends

- [ ] **Extract `hop3-catalog-core`**: models, loader, taxonomy, policy, and the view-model both renderers consume. Pure Python, no web framework. `packages/hop3-marketplace` depends on the whole of `hop3-server` (Litestar, SQLAlchemy, the plugin manager) to render static HTML today. `hop3-server` keeps everything about fetching, verifying and installing (trust and state); the new package is presentation. The server feature table (catalog versioning, 0.8) stays in hop3-server.

### Catalog growth

- [ ] More applications, now that the packaging playbook and the verification bar exist.
- [ ] `nixpkgs-wrapper` supporting sibling packages (`nixpkgs-packages = {main = "…", assets = "…"}`): unblocks Vaultwarden, WriteFreely and GoToSocial, and is the companion-archive hook that Outline, PeerTube, Funkwhale and Chatwoot will also need.
- [ ] Node/pnpm workspace layouts (ESM/CJS mismatch, dangling virtual-store symlinks): block Directus, HedgeDoc, and future Outline, Strapi and Rocket.Chat.

## Cut from 0.8, second round (2026-10-19)

What was left in 0.8's scope when SF moved it here, so 0.8 tags on its release checks alone ([`plan-0.8.md`](plan-0.8.md#decided-the-remaining-open-work-moves-to-09-2026-10-19)). They come next in the queue, after the first round.

### Installer composability: toolchain versions as a choice (headline 4)

The server shipped one Node version and no pnpm, so umami (needs ≥20) and ghost (needs pinned ≥18.12) could not be packaged natively, and native Outline and Strapi hit the same wall. Per-app `[build].node-version` and a pinned server-wide npm and pnpm are done; what remains:

- [ ] **`hop3-install server --with=nodejs-18|nodejs-22|pnpm|headless-browsers|latex`**, composing with the existing `--with` features (`rust`, `clojure`, `elixir` exist: installed best-effort on every server, and requesting one makes its failure stop the install).
- [ ] **A per-app package manager version.** A recipe cannot ask for a pnpm other than the server's. Etherpad has absorbed three breaking pnpm-10 changes in its download script to compensate; the third, upstream's plugin migration calling `pnpm ls --no-production` (a flag pnpm 10 removed), is a fatal startup error, so it presents as an app that will not boot although the build succeeds. Blocker #33 asks *which* package manager (dispatch from the lockfile); this asks *which version*. The two want deciding together.

  **Experiment before deciding** (SF, 2026-09-25). It takes three steps, each producing a table:

  1. *Inventory.* For every Node recipe in the catalog, native, Docker and Nix, fetch upstream at the recipe's version and record: the lockfiles present and their `lockfileVersion`, the `packageManager` field of `package.json`, any `engines` entry for npm, pnpm or yarn, and what the recipe does today (an overridden install command, a workaround in a script). This says how many apps name their package manager and its version themselves, and how many ship two lockfiles.
  2. *Native build matrix* on Docker, for the apps with a pnpm or yarn lockfile. Build each three ways: today's server-wide pnpm; the version `packageManager` names, through corepack, installed into the app's venv; and a version installed into the venv beside `[build].node-version`. Record whether it builds, starts and passes `check.py`, the build time, and which of the recipe's workarounds can be deleted (etherpad's three are the test).
  3. *Nix.* `node-pnpm-install` takes its pnpm from the nixpkgs pin, which offers one attribute per major (`pnpm_9`, `pnpm_10`). Build directus-nixgen and etherpad-nixgen with each major and with the major `packageManager` names, and check whether the major is enough for the lockfile.

  What decides: the mechanism that removes the per-recipe workarounds, gives the same answer on both builders (so at most a major on the Nix side, since the sandbox cannot download a pnpm), and fails at build naming the version it could not provide. Corepack downloads the package manager at build time: acceptable on the native builder, not in the Nix sandbox, and that asymmetry is part of what the matrix measures.
- [ ] **Kernel sysctls the platform requires** (`vm.max_map_count` for bundled Elasticsearch): unblocks SonarQube and anything Elasticsearch-shaped.

### Roles and the sign-in gate: what remains

- [ ] **Bearer tokens for scripts** calling a gated API, the gate's remaining open question (ADR 062).
- [ ] **Caddy and Traefik in the installer**: an admin-domain route for each, Traefik's `aliasHeadersStrategy: delete` (the gate relies on it), and certificates made proxy-aware. certbot issuance and renewal are wired to nginx only, so both are refused elsewhere today.
- [ ] **Per-app roles**, designed into ADR 061 and not built: a deployer reaches every app on the server.
- [ ] **Where the gate runs regularly.** `180-flask-gated` needs an admin domain, so the Docker target and a server addressed by IP leave it out. Either target the box by its hostname and include the fixtures, or give those targets an admin domain of their own ([`../todo.md`](../todo.md)).

## Security and identity

**Per-app users and build-time isolation (ADR 055).** Each app runs as its own Unix user, its run-time commands and its builds included, with `src/` read-only to it. 0.8 stops app code reaching root through hop3-rootd; apps still share `hop3`, so one can read another's data and the control plane's until this lands. Work plan: [`plan-0.9-per-app-users.md`](plan-0.9-per-app-users.md); every switch of user goes through hop3-rootd. The ADR's open questions (UID allocation and reuse after destroy, single-user Nix) are settled there before code.

**Per-resource ownership (`App.owner`).** Ownership recorded on the row, dispatcher-level authorization, and a migration for existing applications. Needs its own ADR. ADR 011 notes that per-tenant encryption keys only become meaningful once the control plane distinguishes accounts, so this gates that too.

**SSO / identity management.** Evaluate Canaille as an IDM component, design an OAuth2/OIDC gateway, prototype. A related item, **MFA (ADR 012)**, is deferred with a settled design (TOTP gating token issuance, U2F/FIDO2 above it) and its stated trigger is the dashboard becoming the primary administrative surface. The 0.7 acceptance campaign, in which all twenty catalog applications were installed by hand through the web interface, suggests that trigger is already met, so the deferral should be revisited.

**CSRF tokens.** Today `samesite=lax` plus the invariant that every mutation is a POST stands in for them, and a route-map test enforces the invariant. Tokens are the belt to that pair of braces.

## Runtime and isolation

**An isolation ADR, before any isolation code.** chroot versus systemd-nspawn versus bubblewrap versus micro-VMs versus rootless OCI, with trade-offs and a recommendation. Several of these appear on wish-lists (`../todo.md`); none should be built before the comparison is written, and writing it is about a day. ADR 055 §9 places namespace isolation as a heavier decision *building on* UID separation, so the 0.8 work comes first regardless.

**Alternative runtimes and backends.** Podman rootless or youki would run the OCI images Hop3 already produces without a `dockerd` dependency. systemd-nspawn or bubblewrap would give each application its own dependency tree. Micro-VMs serve the multi-tenant case. A Docker backend could also do without compose. Each waits on the ADR above.

**Runtime stack replacement (ADR 023).** Granian plus Caddy plus a purpose-built process manager, replacing uWSGI plus nginx plus supervisor. uWSGI is unmaintained, cannot be reconfigured while running, and serves Hop3 with only a handful of its features. Partial groundwork exists: the Caddy plugin is in tree and Granian already serves `hop3-server` itself. It stays large and its open questions are unanswered: Granian's production maturity, a zero-downtime migration for existing deployments, and what replaces uWSGI's rack and JVM plugins for Ruby, Node and Go applications. It also interacts with whatever ADR 055 settles, since that rests on the Emperor. **The benchmark and the migration design would make this real.** Before a purpose-built process manager, [`process-runner-alternatives.md`](../process-runner-alternatives.md) surveys the existing runners (systemd through rootd, s6, supervisord) against what uWSGI does for Hop3.

## Operations

**Recipe upgrades for installed catalog applications.** An application installed from the catalog keeps no record of the recipe it came from: `hop3 catalog install` copies the recipe into `src/` once, and refuses to run again over an application that has deployed successfully. Nothing else reaches it. The only path to a newer recipe is `hop3 app destroy`, which deletes the application's data, followed by a fresh install. So a catalog fix reaches new installs only, security fixes included. The September 2026 passes removed `APP_KEY`s shared by every install, a Jenkins that ran with no security realm, and forges that rewrote the control plane's `authorized_keys`. None of that reaches an application already running. Until this exists, a catalog fix that matters to running installs has to be announced, with the steps to apply it by hand.

What there is to build on:
- `_restage` (`server/catalog/install.py`) already re-stages a recipe over an existing application while keeping its identity (hostname, generated secrets, addons, environment), for installs whose first deploy failed.
- Since 0.8, a deploy that replaces `src/` fills a newly declared volume from the tree it replaces, so a recipe that moves data into a volume takes the data with it.
- `requires_hop3` refuses a recipe that needs a newer server, while the signed index holds a serial and a digest of every file (ADR 049).

The proposal has four parts:
- Record the origin at install: catalog id, serial, and a digest of the recipe as staged.
- `hop3 catalog upgrade --app <name>`: check `requires_hop3`, show what changes, re-stage the current recipe the way `_restage` does, and deploy.
- Say when an installed recipe is behind the catalog, in `hop3 app show`, `hop3 catalog list` and the dashboard.
- A changelog entry per published recipe change, marking the ones that need the operator to act. Grafana's generated `secret_key` (September 2026) is such a case: datasource credentials stored under the old key have to be entered again.

These questions are undecided:
- **Who triggers an upgrade.** Manual only is the least surprising, but a fixed vulnerability then waits on each operator noticing it. A notice buys attention without taking control. Applying security fixes automatically closes the window and takes a change out of the operator's hands. What decides: whether the catalog can tell a security fix from any other change, which the changelog entry would have to record.
- **How a recipe version is named.** The digest costs nothing to maintain but cannot say which of two recipes is newer or which change broke something; a revision number orders changes and anchors the changelog, at the cost of a bump on every change, which the recipe lint could enforce. What decides: whether operators need to skip or pin versions.
- **Local modifications.** An operator who pushed their own changes to the application no longer runs the catalog recipe. An upgrade would overwrite those changes. The recorded digest detects it; whether that refuses the upgrade, offers a merge, or proceeds on `--force` is open.
- **A failed upgrade.** Keeping the replaced tree aside until the new deploy succeeds (as a deploy already does until the volumes are linked) makes rolling back possible; whether 0.7's upgrade-with-automatic-rollback covers a re-staged recipe decides how much of this is new.

It adds fields to the application record and a command whose failure modes reach data, so it needs a short ADR, alongside ADR 049. The naming should agree with the `upgrade`/`downgrade` vocabulary ADR 032 settles below.

**Deployment strategies (ADR 032).** Blue-green and canary appear in an accepted ADR and nowhere in the source, alongside `revert`/`upgrade`/`downgrade` naming over `current`/`previous`. 0.7 shipped upgrade-with-automatic-rollback, which covers the operationally urgent part; the rest is optional for a single-server platform, which is why it sits here.

**Backups, phases 2 and 3 (ADR 016).** Scheduled backups and retention policies first; then remote storage (S3, B2), encryption, and incremental backups. Phase 1 shipped in 0.7 including cross-instance restore. Phase 2 is small and pairs naturally with the control-plane audit log above.

**Supply chain (ADR 013).** Signature attestation for release artefacts and for the SBOM (Sigstore, in-toto, cosign), scheduled reproducible-builds verification, and upstream source mirroring against registry deletions. The Cyber Resilience Act imposes an external deadline on attestation, which makes this the item here most likely to become urgent for reasons that have nothing to do with our own priorities.

**HTTPS in the test lab.** Applications that force HTTPS can only be redirect-verified over plain HTTP today, so their content is never actually checked. This blocks a class of applications from the corpus.

## Platform reach

**Reproducibility beyond x86_64.** The bit-for-bit rebuild property is measured on one architecture. An ARM-class target means vendoring a second dependency set per template. The work is mechanical and a prerequisite for anything edge-shaped.

**Toolchain breadth.** A `.NET` toolchain exists but no corpus application exercises it; Clojure and Elixir are in the same position. Each is a real packaging gap the moment an application needs it.

**The Docker corpus at the sign-in bar.** Recipes exist for most of the twenty catalog applications and none has ever been verified by signing in. Nothing claims this variant as measured. Measuring it is a campaign. The two families that *have* been measured both failed comprehensively on first contact, so it remains a known unknown.

## Smaller, self-contained

- **Web terminal (ADR 005, deferred).** In-browser log streaming and interactive shells. The original implementation was removed during the Litestar migration; the specification remains. The streaming infrastructure it waited on now exists.
- **Web analytics for deployed applications:** integrate an existing tool, or offer one as an addon.
- **`sslip.io` as a default hostname**, so a fresh deployment is reachable without configuring DNS first.
- **A shared download helper.** 27 application scripts still use a bare `curl -s` without `--fail` or retry, so an HTTP error yields a truncated file and an unclear build failure.
- **Retire the deprecated command spellings.** Several concepts are still reachable under more than one name; the documentation check found most remaining uses in our own guides, few in user scripts.

## Corpus tail

- The applications the catalog files as `broken` each have a `DEFERRED.md` naming their blocker. Every platform fix should trigger a re-try of the applications it unblocks; a `--filter-blocker` selector in the test runner would make that mechanical.
- Two Ruby test applications and a source-built `wiki-js` variant remain unconverted from an earlier packaging pass.
