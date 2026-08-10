# Plan: 0.7.x: maintenance, catalog polish, and the loose ends of 0.7

**Created:** 2026-08-01. **Owner:** SF. **Horizon:** the next days-to-weeks, ahead of 0.8 in September.
**Predecessors:** [`../ngi-2024/release-plan-0.7.md`](../ngi-2024/release-plan-0.7.md) (the annex tracker, what gated the tag), [`../security/backlog-2026-08-01.md`](../security/backlog-2026-08-01.md) (the security items left open after the 2026-07 rounds), [`../reports/paper-completion-plan.md`](../reports/paper-completion-plan.md) (its *Postponed past 0.7* section).
**Successor:** [`plan-0.8.md`](plan-0.8.md): features wait for 0.8; fixes belong here.
**Later:** [`plan-0.9-plus.md`](plan-0.9-plus.md) (the queue behind 0.8) and [`parked.md`](parked.md) (directions deliberately not scheduled).

## What this release line is for

0.7.0 shipped on 2026-07-31 as the final NGI deliverable release. 0.7.x is the tail: **fixes, small gaps, and presentation work on what 0.7 already ships**. The test for admission is whether an item repairs or completes something a 0.7 user can already see. Anything that adds a capability waits for 0.8, even when it is small.

**0.7.1 was tagged on 2026-08-02** with the security payload. The catalog (the most visible thing 0.7 added) was left with presentation defects no automated gate caught, because every gate we built asks one thing: does the app *deploy and sign in*? Whether its entry *looks like something an operator would install* is a question none of them posed. The answer, when someone finally looked on 2026-08-02, was that all 55 entries rendered with no tags, no memory, no services, no icon and one category between them.

**Updated 2026-08-03**: §2 is done. The data was fixed (§2.3, §2.4), the work grew a public face at `apps.hop3.cloud` sharing the dashboard's loader (§6), a publish-time gate now blocks a bad entry from being signed (§2.2), and the dashboard renders what the entry declares (§2.3). Both defects of the underlying kind (nobody had looked, and nothing would have told us) now have a check behind them. Under §2, two deferred judgement calls remain: whether variants deserve their own entries (§2.1) and re-capturing the nine single-capture entries.

**Updated 2026-08-09**: both "ship it" items are shipped. 0.7.1 is on PyPI (`hop3-server` 0.7.1 is the latest release there, alongside the rest of the workspace), and `apps.hop3.cloud` serves the generated gallery rather than the placeholder, so §1 and §6's publish item are closed. The open-registration defect (§4) is closed too: all six forge recipes in the catalog declare `DISABLE_REGISTRATION`, the Nix variants included, and the signed `dist/index.json` was built after them — what survives there is the design question, not a shipped defect. With those out of the way the front of the queue is **§3, the security backlog**, and the `git clone` caps are the item to take first. 0.7.2 then has a shape: the three fixes already sitting in `CHANGES.md [Unreleased]` plus whatever of §3's robustness trio lands.

## 1. Ship 0.7.1 (the security payload)

Four fixes are landed and unreleased (`CHANGES.md [Unreleased] § Security`, commit `2dee5209`): the shared `AUTH_RATE_LIMITER` across the web form and `auth get-token`, identical bcrypt-timed responses for all three login failures, an up-front refusal when a `Secure` cookie would be dropped over plain HTTP, and `GET /auth/logout` converted to a form POST. They affect every release up to and including 0.7.0.

- [x] Add the Bugsink recipe fix (`5145085e`) to the changelog: two-process deploy via `before-run` plus `[run.workers] snappea`. It was the only non-doc change since the tag that the changelog did not mention.
- [x] Decide F6 and land it in the same release (§3), so the security section is complete.
- [x] Changelog closed out as `[0.7.1] - 2026/08/02`, versions bumped across the workspace, lockfile synced. No blog post; this is a patch release, and the changelog section is the release note.
- [x] `hop3-tooling` was a release behind (0.6.2 at the 0.7.0 tag) because it was absent from *both* release scripts' hardcoded package lists, and nothing checks a package in neither. `bump_version.py` now derives the workspace from `packages/*` directly, and `release.py`'s alignment gate covers every member, published or not.
- [x] **0.7.1 tagged and published.** `make release` has run; 0.7.1 is the latest `hop3-server` on PyPI, so the security payload is in users' reach and no longer sits behind a tag.

Landed after the tag, unreleased, in `CHANGES.md [Unreleased]`: an `HOP3_SECRET_KEY` under 32 bytes is refused at signing time; `APP_START_TIMEOUT` actually reaches the reconciler (it was constructed without it, so the setting did nothing); and Forgejo's licence is corrected to `GPL-3.0-or-later`. All three were harvested from an abandoned branch (see §9).

**Ship this first:** a released security fix that sits unreleased carries a real cost to users. Everything else in this plan can ship in 0.7.2. *Done 2026-08-09.*

## 2. The catalog: from "installs" to "browsable"

The catalog's *functional* story is done and gated (every app installs from the signed catalog and is verified by signing in). The remaining work is the presentation, which an operator sees first.

### 2.1 55 entries, 20 applications: kept, deliberately

`dist/index.json` carries **55 entries** for twenty applications, because each is published in up to three packaging variants (`bookstack`, `bookstack-nix`, `bookstack-nixgen`).

**Decided 2026-08-03: the variants stay for now**, so an operator can install the same application built three ways and compare them. That makes the count intentional, and the "twenty curated apps" claim needs to say *applications*, not entries, wherever it appears.

The variants did not describe themselves; that was the real defect, and it is fixed: fifteen of the thirty-five carried no `[metadata]` section at all, so the catalog published an app titled `Bookstack-Nix` with no version and no description. The generator now grafts the application's identity (`[metadata]`, and the `homepage` / `license` / `author` fields when a recipe declares its own block) from the native entry, and never propagates `featured`: one application should not take three front-page slots.

- [ ] Revisit whether the catalog should show one entry per application with the build path as a choice inside it. Deferred, not cancelled; it changes an artefact deployed servers already consume, so treat `index.json`'s shape as an API and decide it in ADR 049 before implementing.

### 2.2 A consistency check, run before publish: done

Every catalog defect so far was found by a person looking at the page. `hop3-tools catalog` already has `drift` (shipped ≡ tested), `reports` (experience-report headers), `promote` and `verify`; there was no check on the *presentation* metadata.

- [x] `hop3-tools catalog lint` asserts, per entry: a title, description and version; a category from the known taxonomy and not `Other`; tags; a `memory` estimate; an icon; at least one screenshot. Plus one rule the review added: **no two entries may claim the same id**: the service keys apps by id, so the second silently replaces the first and an application vanishes with nothing logged. It reports every violation and names the app.
- [x] Wired into the catalog repo as `make lint-presentation`, which `validate` runs and `build` depends on, so a bad entry cannot be signed. Verified by planting `category = "Other"` on isso: the build stops.

Its first real run found three entries with no version (keycloak-nix, keycloak-nixgen, mattermost-nixgen), whose versions come from the pinned nixpkgs rather than the recipe. Read off the pin (`50ab7937` = nixos-24.11): keycloak 26.1.4, mattermost 9.11.16, which confirms that grafting the native version would have published a false claim, since native mattermost is 9.4.2.

**Note the ordering trap**, which has caught us before: `check-catalog.py` installs from the **published** catalog, so editing `apps/` and re-running silently re-tests the old recipe. The lint runs at publish time for the same reason, and says so when it fails.

### 2.3 The metadata the catalog carried and never showed: done

The presentation gap turned out to be one defect, not five. `catalog.toml` was **never read by hop3-server**: the loader asked for `[metadata].author/website/tags`, `[resources].memory`, `[port].web` and `[[provider]]`, none of which the recipes use. Measured on 2026-08-02, all 55 entries loaded with no tags, no memory, no services, no icon, and category `Other`; only title, description and version survived.

Fixed by reading the overlay, following `homepage`, and taking services from `[[addons]]`, the spelling recipes actually use. Every field is now populated across all 55 entries, and the catalog carries an icon (19 sourced from the icon corpus, isso rasterised from its upstream SVG), an upstream `author` per application, six `featured` picks spanning six categories, and no app left in `Other`.

The loader lists each app's own `screenshots/` directory, sorted, under the same containment rules as the icon path (inside the app's verified directory, raster only, no SVG). All 101 captures surface with nothing to maintain; `[catalog].screenshots` remains an override for a subset or a different order.

- [ ] Re-capture the nine single-capture entries (invoice-ninja, uptime-kuma, and the mattermost / radicale / easy-appointments Nix variants), or declare each `unsupported` with its reason.
- [x] **The dashboard now shows what the entry declares.** Its templates read `app.initials_bg_color`, `app.long_description` and `app.min_memory` (three names the model has never defined, rendered blank by Jinja), so the fallback icon drew on `background-color: ;` and the memory row never appeared. A fourth of the same shape: the templates compared `resource_tier` against `lightweight`/`moderate` while the model produces `light`/`medium`, so every app was styled heavy and the tier filter matched nothing. Screenshots now render through `/dashboard/catalog/screenshots/{id}/{filename}`, which selects from the names `find_screenshots` found, and the readme (already sanitised at load, already shown on the public site) renders as the long description.

  The two front-ends now describe an application identically. The class of defect (a template naming a field nobody has, silently rendering empty behind a 200) is gated. `test_templates.py` checks every `app.foo` in the catalog templates against the model (via the Jinja AST) and every Alpine `app.foo` against `to_dict()`'s keys, and pins the tier vocabulary to what the model can produce.

### 2.4 Categories: done

Categories had two sources of truth: the declared `[catalog].category` and a tag-derived mapping in `server/catalog/taxonomy.py` that silently overwrote it. The declared value now wins, the mapping handles tags only, and the corpus files under **13 categories** with none in `Other`.

## 3. Security backlog (the items left open on 2026-08-01)

From [`../security/backlog-2026-08-01.md`](../security/backlog-2026-08-01.md). Two decisions, three robustness fixes and two process items; all small.

- [x] **F6: magic-link consumption order.** Decided 2026-08-02: consumption-on-presentation stands, and the documentation was the defect. security-model.md §3.7.2 now states the rule covering this case and the plain-HTTP one together (refuse before consuming when the holder can remove the obstacle within the token's life; consume when they cannot), with a unit test pinning the ordering. Shipped in 0.7.1.
- [ ] **SMTP credentials versus threat-model invariant 8.** `smtp_password` is a plain `str` injected as `SMTP_PASSWORD` / `EMAIL_HOST_PASSWORD` / `MAIL_PASSWORD` (`plugins/email/email.py:96,436,444,452`), while invariant 8 claims Fernet encryption at rest for credentials. `security-model.md` §3.4 documents the platform-wide deferral; the threat model does not carve the exception. **This is the only place the docs claim more than the platform delivers**, so it is a correctness issue in the documentation regardless of which way it is resolved: either encrypt the field or amend the invariant.
- [x] **`git clone` now has a timeout, a depth limit and a size cap** (2026-08-09). `clone_repository` runs it shallow and single-branch under both caps, in its own process session so a kill takes the transport helpers with it, and removes the partial tree on any failure — a cap that keeps the bytes it refused has capped nothing. The finding pointed at `core/git.py:158`, which turned out to be inside a `GitManager.clone()` **nobody calls** (now deleted); the reachable clone is `app create <repo_url>`, and it was passing the URL to git **unvalidated**, so `ext::sh -c …` (git runs it), `file:///…` and a leading `-` all reached the command line. `validate_repo_url` guards it now, and the call site's cleanup — which caught `ValueError`, a thing a failing clone never raises — no longer leaves a registered app whose source never arrived. Written up as security-model.md §3.1.5.
- [x] **Streaming deploy no longer spawns unbounded background build threads** (2026-08-09). One bounded `BuildQueue` sits between a deploy and its build: `MAX_CONCURRENT_BUILDS` run at a time (default 2), `MAX_WAITING_BUILDS` wait (default 32), and a deploy past that is refused rather than queued. Both states are visible where the operator is looking — a refused deploy finishes its own stream carrying the reason, and a queued one writes how many are ahead of it, since a build that has not started is indistinguishable from one that has stalled. All three callers (`hop3 deploy`, `hop3 catalog install`, the dashboard form) share the queue, so §8's background auto-deploy now has the bounded executor it was blocked on. security-model.md §3.3.4.
- [x] **Redis db-number allocation no longer races, and a failed create no longer eats a slot** (2026-08-09). Choosing the number and writing it down now happen in one critical section under an exclusive `flock` on the addon-secrets directory; before, allocation returned a number and the caller persisted it three Redis round trips later, so ten concurrent claims all got db 1 — ten apps in one database, mixing keys, with nothing to notice. A create that fails after claiming releases the number, and the all-fifteen-taken message names which addon holds each. It also corrected security-model.md §3.1.4, which asserted that persistent assignment precluded the collision: the model claimed a property the code did not implement, which is the same shape as §3's remaining SMTP item.
- [ ] **Re-run the audit over what the 2026-07-29 review's byte ceiling dropped**: `hop3-installer`, `hop3-testing` and `hop3-tui` were entirely out of scope, the email and Docker plugins partially covered, and `plugins/nix/` may not have been reached. The backlog calls this the highest-value review action available, and it is cheap.
- [ ] **Close findings in all three places** (backlog, security-model/threat-model, and the originating report). A pass over `report-2026-05.md`, `report-2026-07-21.md` and `report-2026-07-29.md` for stale "open" markers.

**Explicitly not in 0.7.x, by decision (SF, 2026-08-01):** relocating `hop3-rootd` out of the `hop3`-writable venv, per-resource ownership (`App.owner`), the control-plane audit log, per-app UID separation (ADR 055), and CSRF tokens. All are platform work; the audit log and UID separation are in [`plan-0.8.md`](plan-0.8.md), and the other three await a decision on where they land.

## 4. Diagnostics and verification gaps

- [x] **The specific start-failure diagnosis now leads.** It is computed before anything is printed, and travels three ways: the headline (`→ the app's port (8123) is listening but it did not answer an HTTP request…`), the `Abort` reason, and (the one that mattered) `app.error_message`, which is all the dashboard and `hop3 app status` show. Previously the operator's only view read `failed to start within 240s` with no cause, which is how three `start-timeout` bumps (120 → 180 → 240) were spent on the one setting that was not the problem. Two regression tests, both confirmed failing against the old ordering.
- [x] **`[healthcheck].contains` populated across 100 recipes** (101 of 154 now assert content, up from 2). The values were not invented: each is the string that recipe's own `[[test.validations]]` already asserts *on the same path*, restricted to validations expecting 200: a string the deployed app is known to serve. Verified by deploying gitea, adminer and isso on Docker (3/3), gitea included deliberately because its admin-bootstrap and probe steps are the case where start-time content could differ from validation-time content.
  Also: when no `contains` is declared the deploy now reports "readiness accepted any HTTP status … an error page or a placeholder would have passed"; the old message was an unqualified "App is now running".
- [ ] **53 recipes still assert nothing at start**, because their content assertion sits on a path the healthcheck does not probe: 43 outright, plus 10 whose `/` validation expects a 302 or 400 (isso, kanboard, invoice-ninja across variants: `/` is a redirect or not a page for these). The fix is the same for all 53 and needs per-app judgement: point `[healthcheck].path` at something that returns 200 with content.
- [ ] **A publish-time gate for the above.** Deliberately not added yet: only 30 of the catalog's 55 entries can derive a `contains` today, so the rule would block `make publish`, which is the release itself. Add it once the catalog recipes are reconciled ([plan 34](../../local-notes/plans/34-apps-single-source.md)).
- [ ] **Make `DISABLE_REGISTRATION` a platform concern.** The shipped defect is closed: all four Nix forge variants now declare it in the config they generate (`[service]` in the hand-written recipes, `[nix.config-files.sections.service]` in the generated ones), the catalog copies carry it, and the signed index was built after them; a deployed instance answers `GET /user/sign_up` with the disabled notice. What remains is the reason it happened — the setting lived in a `scripts/` directory only one packaging carries, so it was declared four times and could be missed a fifth. Express an application's security posture once, where every variant inherits it. The sign-in bar cannot catch a regression here (an app with open registration signs in perfectly), so the expression *is* the guarantee.
- [ ] **Isso ships no built frontend under Nix**: the `python-venv` template has no frontend build phase, so the admin dashboard serves a 200 whose JavaScript 404s, and a `contains` assertion passes on it.
- [ ] **Easy!Appointments cannot be verified by either path**: no form inputs in the served page for `check.py`, and the browser harness stays on the JS-built form. Needs a check that queries the application without driving its interface. It is the corpus's one standing failure.

## 5. Corpus and coverage

- [ ] **Uptime Kuma has one variant only** (native): no hand-written Nix recipe and no template one. It is the single largest coverage hole in the catalog twenty.
- [ ] **Migrate Vaultwarden and GoToSocial to the template.** Both are expressible now that `[nix].let-extra` and `[nix].env-exports-raw` have landed (reference user: `apps/real-apps-nix-gen/keycloak`), but both still carry a hand-crafted `hop3.nix`.
- [ ] **Record WriteFreely's deferral properly.** The `nixpkgs-wrapper` template has no hook for fetching a companion archive (`templates/pages/static`); Outline, PeerTube, Funkwhale and Chatwoot will hit the same pattern. The hook itself waits for 0.8. Record the deferral now.

## 6. Dissemination tail

- [ ] **Re-record the screencasts (M5.6).** 68 asciicasts are published covering every demo and tutorial; the review pass found 11 ran to completion, 33 end on a visible failure and 24 recorded nothing. Both causes are in the recorder: a fixed 120-second step timeout that 30 tutorials hit at their deploy step, and a manifest that reported success for a file it had written without reading. Fix both, then re-record; the recordings are the deliverable and the harness fixes are a prerequisite for the work.
- [ ] Upload to asciinema.org and capture the URLs; publish to the site and embed in the getting-started docs.
- [x] **Application gallery: built, pending publish.** `apps.hop3.cloud` already existed as a Hop3-deployed static app serving the signed catalog and a "coming soon" placeholder. It now has a site: `packages/hop3-marketplace` renders the catalog to static HTML (55 app pages, 13 category pages, 78 tag pages, a client-side search index, icons and screenshots), and `make site` in the catalog repo writes it into `public/`, wired into `make publish` ahead of `stage`.
  The generator has **no models, loader or taxonomy of its own**: it imports `hop3.server.catalog`, so the public site and the dashboard cannot describe an application differently. That sharing is the point, and the reason the dashboard's own rendering gaps (§2.3) now stand out.
- [x] **Published.** `apps.hop3.cloud` serves the generated site (the app pages, categories and search index, not the 272-byte placeholder), which also makes TR-03 §9's Figure 3 a description of something a reader can visit.

## 7. Developer-facing chores

- [ ] **Pin runtime dependencies.** Workspace packages still use floors (`litestar[standard]>=2.22.0`). Hop3 is an application; pip's `only-if-needed` strategy has left stale transitive deps on servers, and developer machines drift from production. Shape: a `uv pip compile` lockfile consumed by the installer's pip step, bumped deliberately. Scoped to 0.5 prep originally and never done (`../todo.md`).
- [ ] **Add `hop3 validate`.** A client-side lint of a project's `hop3.toml`: schema validation, the committed-credential tripwire, host-safety checks, with no server required, for CI gating. Top-level and project-rooted; the app id is `[metadata].id`. While there, decide whether the stale `hop3 config show` / `config export` ideas in ADR 027 are still wanted or should be struck.
- [ ] **Bring `docs/scripts/` and `scripts/` into the linted set**, or decide deliberately that they stay out. `make ruff` covers only `packages/*/src` and `packages/*/tests`; `preprocess_markdown.py` carries eight ruff findings nobody sees, and `scripts/{bump_version,release}.py` another 27, including `subprocess.run` without an explicit `check` in the code that publishes releases.

## 8. What the abandoned `feat/marketplace` branch still held

A branch on sourcehut, last touched 2026-06-24 and 519 commits behind main, held nineteen commits none of which had an equivalent in main, including the fix for §2.3's blank-metadata defect, written six weeks before the defect was diagnosed here. The catalog repo's validator was pinned to it, so the publish gate had been running **hop3-server 0.5.0's rules against a 0.7 catalog**; re-run under current rules, all 55 apps pass, so the stale pin was hiding nothing.

Harvested: the overlay loader (ported, not cherry-picked, and with its log-and-continue on a malformed overlay changed to a refusal), the `HOP3_SECRET_KEY` length check, the reconciler timeout wiring, and the Forgejo licence. Superseded and dropped: stateful sessions, `serve --workers` (which would now fight the single-worker rate-limiter invariant), two migrations, and the magic-link URL change.

**The licence commit was itself half wrong**, which argues for reading a branch before merging it. Forgejo's `MIT` was a fossil from before its v9 relicensing, but Mattermost's `MIT` was correct; their `LICENSE.txt` grants the compiled binaries we ship under MIT, and the branch's change to AGPL-3.0 would have been a regression. The value now carries the reasoning in the recipe, because this is the second time someone has reached for AGPL.

- [ ] Re-decide the five dashboard features the branch built and nobody re-did: a display title on the installed app, a `DEPLOYING` state so the dashboard can show build progress, background auto-deploy (the bounded executor it needs now exists — `deployers/build_queue.py`, §3), the title in the app list, and defaulting an installed app's name to its blueprint id.
- [ ] Delete the branch once harvested, and record what was taken, so the next person who finds it does not redo this analysis.

## 9. Evaluation and report follow-through

Tracked in full in [`../reports/paper-completion-plan.md`](../reports/paper-completion-plan.md) § *Postponed past 0.7*. Only the items that could plausibly land in a 0.7.x window are repeated here:

- [ ] **Pin the evaluated snapshot and mint the Zenodo DOI**, then finalise TR-03 §8.3 against the pinned tag.
- [ ] **B7: the nixos-25.05 pin bump**, re-run with a per-application disposition recorded under `notes/benchmarks/`, so §6.2's pin-ownership paragraph can quote a number.
- [ ] **Internal review of the revised TR-03; archive on HAL.**

The measurement work proper (per-cell repeats, the memory-versus-app-count curve, peer baselines, the fresh-box three-stack re-measure) is a campaign. It stays in the paper plan.

## Out of scope for 0.7.x

In [`plan-0.8.md`](plan-0.8.md): per-app UID separation (ADR 055), a production PHP runtime, local-source Nix builds, installer composability, the control-plane audit log, email productization, monitoring, the CLI finish (ADR 047), the runtime-stack replacement (ADR 023), SSO/IAM, alternative backends (podman, systemd isolation, microVMs), and the Nix companion-archive fetch hook.

In [`plan-0.9-plus.md`](plan-0.9-plus.md): the second UID-separation increment, SSO and MFA, the isolation ADR, deployment strategies, backups phases 2–3, and supply-chain attestation.

In [`parked.md`](parked.md), not scheduled at all: the agent model and reconciliation (ADR 017, ADR 029), multi-component applications (ADR 038) including any extension of `[run.workers]` to per-process environment, ports or limits, and the generator's system-closure output target (TR-03 §9.7).
.
