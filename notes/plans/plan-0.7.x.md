# Plan: 0.7.x: maintenance, catalog polish, and the loose ends of 0.7

**Created:** 2026-08-01. **Owner:** SF. **Horizon:** the next days-to-weeks, ahead of 0.8 in September.
**Predecessors:** [`../ngi-2024/release-plan-0.7.md`](../ngi-2024/release-plan-0.7.md) (the annex tracker, what gated the tag), [`../security/backlog-2026-08-01.md`](../security/backlog-2026-08-01.md) (the security items left open after the 2026-07 rounds), [`../reports/paper-completion-plan.md`](../reports/paper-completion-plan.md) (its *Postponed past 0.7* section).
**Successor:** [`plan-0.8.md`](plan-0.8.md): features wait for 0.8; fixes belong here.
**Later:** [`plan-0.9-plus.md`](plan-0.9-plus.md) (the queue behind 0.8) and [`parked.md`](parked.md) (directions deliberately not scheduled).

## What this release line is for

0.7.0 shipped on 2026-07-31 as the final NGI deliverable release. 0.7.x is the tail: **fixes, small gaps, and presentation work on what 0.7 already ships**. The test for admission is whether an item repairs or completes something a 0.7 user can already see. Anything that adds a capability waits for 0.8, even when it is small.

The security fixes in `CHANGES.md [Unreleased]` are landed but unreleased, so users are running without them; that alone justifies 0.7.1 soon. And the catalog (the most visible thing 0.7 added) has presentation defects that no automated gate catches, because every gate we built asks one thing: does the app *deploy and sign in*? Whether its entry *looks like something an operator would install* is a question none of them pose.

## 1. Ship 0.7.1 (the security payload)

Four fixes are landed and unreleased (`CHANGES.md [Unreleased] § Security`, commit `2dee5209`): the shared `AUTH_RATE_LIMITER` across the web form and `auth get-token`, identical bcrypt-timed responses for all three login failures, an up-front refusal when a `Secure` cookie would be dropped over plain HTTP, and `GET /auth/logout` converted to a form POST. They affect every release up to and including 0.7.0.

- [x] Add the Bugsink recipe fix (`5145085e`) to the changelog: two-process deploy via `before-run` plus `[run.workers] snappea`. It was the only non-doc change since the tag that the changelog did not mention.
- [x] Decide F6 and land it in the same release (§3), so the security section is complete.
- [x] Changelog closed out as `[0.7.1] - 2026/08/02`, versions bumped across the workspace, lockfile synced. No blog post; this is a patch release, and the changelog section is the release note.
- [x] `hop3-tooling` was a release behind (0.6.2 at the 0.7.0 tag) because it was absent from *both* release scripts' hardcoded package lists, and nothing checks a package in neither. `bump_version.py` now derives the workspace from `packages/*` rather than mirroring the glob by hand, and `release.py`'s alignment gate covers every member instead of only the published subset.
- [ ] Tag and publish (`make release`).

**Ship this first:** a released security fix that sits unreleased carries a real cost to users. Everything else in this plan can ship in 0.7.2.

## 2. The catalog: from "installs" to "browsable"

The catalog's *functional* story is done and gated (every app installs from the signed catalog and is verified by signing in). The remaining work is the presentation, which an operator sees first.

### 2.1 The consistency bug: 55 entries where there should be 20

`hop3-catalog/dist/index.json` carries **55 entries** where the project advertises twenty. The three packaging variants of each app (`bookstack`, `bookstack-nix`, `bookstack-nixgen`) are published as separate installable entries: nothing in `catalog.toml` marks a variant, and neither `server/catalog/loader.py` nor `service.py` filters them. An operator browsing the dashboard therefore sees Bookstack three times and has no way to tell which to pick.

This is the sharpest item in the plan: it is a correctness bug in the published artefact, it undercuts the "twenty curated apps" claim everywhere it is made, and it is the reason to build a consistency check into the publish path.

- [ ] Decide the model. Preference: one catalog entry per application, with the build variant as an *attribute* of the entry (the recipe the installer picks). The alternative (a `hidden = true` / `variant-of = "bookstack"` field in `catalog.toml`) is less work and leaves the variants installable by id for testing.
- [ ] Implement, and assert the published entry count matches the advertised set.

### 2.2 A consistency check, run before publish

Every catalog defect so far was found by a person looking at the page. `hop3-tools catalog` already has `drift` (shipped ≡ tested), `reports` (experience-report headers), `promote` and `verify`; there is no check on the *presentation* metadata.

- [ ] Add `hop3-tools catalog lint` (or extend `drift`) asserting, per entry: a category from the known taxonomy and not `Other`; a non-empty description; an icon; at least one screenshot; a `memory` estimate; and that the entry's id resolves to a recipe. Fail the publish on any violation.
- [ ] Wire it into the catalog repo's publish path, so the gate runs before the artefact ships.

**Note the ordering trap**, which has caught us before: `check-catalog.py` installs from the **published** catalog, so editing `apps/` and re-running silently re-tests the old recipe. The lint must run at publish time for the same reason.

### 2.3 Icons

There are **zero icon or logo files across all 55 app directories**. `CatalogApp.icon_url` always resolves to `/dashboard/catalog/icons/{id}`, which serves the two-letter initials fallback (`models.py:60`). Every app in the catalog is a coloured rectangle with letters in it.

- [ ] Source an icon per app (upstream logos, respecting each project's trademark guidance; several forbid modification; `license_note` in `catalog.toml` is the place to record any restriction).
- [ ] Decide the format and where it lives: a raster file per app directory is simplest, and the dashboard already accepts only raster icons for the catalog (a deliberate XSS constraint from ADR 049; do not relax it to accept SVG without revisiting that decision).
- [ ] Keep the initials fallback for apps whose logo cannot be redistributed. It should stay a fallback.

### 2.4 Screenshots: the images already exist

Every app directory has a `screenshots/` directory holding real captures (`<app>-01-login.png`, `<app>-02-signed-in.png`) produced by the verification campaign, and every `catalog.toml` says `screenshots = []`. The assets are sitting one directory away from the field that would surface them.

- [ ] Populate `[catalog].screenshots` from the files each app already has, and render them on the catalog detail page.
- [ ] Regenerate where the capture is stale or missing. Known gaps, already diagnosed in the experience reports: Mattermost (harness finds no password field at `/login`), Paheko (capture hangs on a failed ServiceWorker registration), Bugsink; Invoice Ninja (Flutter canvas) and Radicale (identical signed-in rendering) are declared `unsupported` and need no capture. Uptime Kuma's missing signed-in shot is undeclared; declare it either way.

### 2.5 Categories

Categories have two sources of truth: each `catalog.toml` declares `[catalog].category`, and `server/catalog/taxonomy.py` *derives* categories from tags via `CATEGORY_MAPPING`. Three apps currently sit in `Other`.

- [ ] Pick one source. The declared field should win; the tag mapping handles *tags*.
- [ ] Retire `Other` by assigning the three apps real categories, and have the lint (§2.2) refuse it thereafter.
- [ ] Review the full category list for an operator-facing taxonomy: a browsable catalog wants roughly 8–12 categories with sensible populations.

## 3. Security backlog (the items left open on 2026-08-01)

From [`../security/backlog-2026-08-01.md`](../security/backlog-2026-08-01.md). Two decisions, three robustness fixes and two process items; all small.

- [x] **F6: magic-link consumption order.** Decided 2026-08-02: consumption-on-presentation stands, and the documentation was the defect. security-model.md §3.7.2 now states the rule covering this case and the plain-HTTP one together (refuse before consuming when the holder can remove the obstacle within the token's life; consume when they cannot), with a unit test pinning the ordering. Shipped in 0.7.1.
- [ ] **SMTP credentials versus threat-model invariant 8.** `smtp_password` is a plain `str` injected as `SMTP_PASSWORD` / `EMAIL_HOST_PASSWORD` / `MAIL_PASSWORD` (`plugins/email/email.py:96,436,444,452`), while invariant 8 claims Fernet encryption at rest for credentials. `security-model.md` §3.4 documents the platform-wide deferral; the threat model does not carve the exception. **This is the only place the docs claim more than the platform delivers**, so it is a correctness issue in the documentation regardless of which way it is resolved: either encrypt the field or amend the invariant.
- [ ] **`git clone` has no timeout, no depth limit and no size cap**: a bare `subprocess.run(cmd, cwd=cwd, check=True)` at `core/git.py:158`. Any operator-equivalent account can fill the disk via `app create <repo_url>` and take down every app on the host. The sharpest of the three robustness items.
- [ ] **Streaming deploy spawns unbounded background build threads.**
- [ ] **Redis db-number allocation has a race and a slot-exhaustion path.**
- [ ] **Re-run the audit over what the 2026-07-29 review's byte ceiling dropped**: `hop3-installer`, `hop3-testing` and `hop3-tui` were entirely out of scope, the email and Docker plugins partially covered, and `plugins/nix/` may not have been reached. The backlog calls this the highest-value review action available, and it is cheap.
- [ ] **Close findings in all three places** (backlog, security-model/threat-model, and the originating report). A pass over `report-2026-05.md`, `report-2026-07-21.md` and `report-2026-07-29.md` for stale "open" markers.

**Explicitly not in 0.7.x, by decision (SF, 2026-08-01):** relocating `hop3-rootd` out of the `hop3`-writable venv, per-resource ownership (`App.owner`), the control-plane audit log, per-app UID separation (ADR 055), and CSRF tokens. All are platform work rather than maintenance; the audit log and UID separation are in [`plan-0.8.md`](plan-0.8.md), and the other three await a decision on where they land.

## 4. Diagnostics and verification gaps

- [ ] **Print the specific start-failure diagnosis above the generic timeout headline.** `deployer.py:717-745` builds the headline `App '<name>' failed to start within {timeout}s` at :720 and logs the actual diagnosis ("the app's port is listening but no worker is serving") at :737, below `Gathering diagnostic information...`. Three `start-timeout` bumps (120 → 180 → 240) were spent on the wrong line before anyone read the one underneath. The platform diagnosed Bugsink correctly every time and buried it.
- [ ] **`[healthcheck].contains` is declared by no recipe in the corpus**, verified: zero occurrences under a `[healthcheck]` table across `apps/real-apps-nix*/`. The deployer has supported it since 0.7 (`deployer.py:412,526-564`), so a deploy still treats any status line as "serving" and prints "App is now running" for a 500. Populate it across the catalog recipes; this is recipe data.
- [ ] **Make `DISABLE_REGISTRATION` a platform concern.** It lives only in the native recipes' `scripts/setup-config.sh`, and no Nix variant carries a `scripts/` directory, which is how all four Nix forge builds shipped with open registration. The sign-in bar cannot catch it (an app with open registration signs in perfectly). Express it where every variant inherits it.
- [ ] **Isso ships no built frontend under Nix**: the `python-venv` template has no frontend build phase, so the admin dashboard serves a 200 whose JavaScript 404s, and a `contains` assertion passes on it.
- [ ] **Easy!Appointments cannot be verified by either path**: no form inputs in the served page for `check.py`, and the browser harness stays on the JS-built form. Needs a check that queries the application without driving its interface. It is the corpus's one standing failure.

## 5. Corpus and coverage

- [ ] **Uptime Kuma has one variant only** (native): no hand-written Nix recipe and no template one. It is the single largest coverage hole in the catalog twenty.
- [ ] **Migrate Vaultwarden and GoToSocial to the template.** Both are expressible now that `[nix].let-extra` and `[nix].env-exports-raw` have landed (reference user: `apps/real-apps-nix-gen/keycloak`), but both still carry a hand-crafted `hop3.nix`.
- [ ] **Record WriteFreely's deferral properly.** The `nixpkgs-wrapper` template has no hook for fetching a companion archive (`templates/pages/static`); Outline, PeerTube, Funkwhale and Chatwoot will hit the same pattern. The hook itself waits for 0.8. Record the deferral now.

## 6. Dissemination tail

- [ ] **Re-record the screencasts (M5.6).** 68 asciicasts are published covering every demo and tutorial; the review pass found 11 ran to completion, 33 end on a visible failure and 24 recorded nothing. Both causes are in the recorder: a fixed 120-second step timeout that 30 tutorials hit at their deploy step, and a manifest that reported success for a file it had written without reading. Fix both, then re-record; the recordings are the deliverable and the harness fixes are a prerequisite for the work.
- [ ] Upload to asciinema.org and capture the URLs; publish to the site and embed in the getting-started docs.
- [ ] **Application gallery page on hop3.cloud**: the catalog work in §2 is what makes this worth building, since the gallery is the same metadata rendered for a public audience.

## 7. Developer-facing chores

- [ ] **Pin runtime dependencies.** Workspace packages still use floors (`litestar[standard]>=2.22.0`). Hop3 is an application; pip's `only-if-needed` strategy has left stale transitive deps on servers, and developer machines drift from production. Shape: a `uv pip compile` lockfile consumed by the installer's pip step, bumped deliberately. Scoped to 0.5 prep originally and never done (`../todo.md`).
- [ ] **Add `hop3 validate`.** A client-side lint of a project's `hop3.toml`: schema validation, the committed-credential tripwire, host-safety checks, with no server required, for CI gating. Top-level and project-rooted; the app id is `[metadata].id`. While there, decide whether the stale `hop3 config show` / `config export` ideas in ADR 027 are still wanted or should be struck.
- [ ] **Bring `docs/scripts/` and `scripts/` into the linted set**, or decide deliberately that they stay out. `make ruff` covers only `packages/*/src` and `packages/*/tests`; `preprocess_markdown.py` carries eight ruff findings nobody sees, and `scripts/{bump_version,release}.py` another 27 — including `subprocess.run` without an explicit `check` in the code that publishes releases.

## 8. Evaluation and report follow-through

Tracked in full in [`../reports/paper-completion-plan.md`](../reports/paper-completion-plan.md) § *Postponed past 0.7*. Only the items that could plausibly land in a 0.7.x window are repeated here:

- [ ] **Pin the evaluated snapshot and mint the Zenodo DOI**, then finalise TR-03 §8.3 against the pinned tag.
- [ ] **B7: the nixos-25.05 pin bump**, re-run with a per-application disposition recorded under `notes/benchmarks/`, so §6.2's pin-ownership paragraph can quote a number.
- [ ] **Internal review of the revised TR-03; archive on HAL.**

The measurement work proper (per-cell repeats, the memory-versus-app-count curve, peer baselines, the fresh-box three-stack re-measure) is a campaign. It stays in the paper plan.

## Out of scope for 0.7.x

In [`plan-0.8.md`](plan-0.8.md): per-app UID separation (ADR 055), a production PHP runtime, local-source Nix builds, installer composability, the control-plane audit log, email productization, monitoring, the CLI finish (ADR 047), the runtime-stack replacement (ADR 023), SSO/IAM, alternative backends (podman, systemd isolation, microVMs), and the Nix companion-archive fetch hook.

In [`plan-0.9-plus.md`](plan-0.9-plus.md): the second UID-separation increment, SSO and MFA, the isolation ADR, deployment strategies, backups phases 2–3, and supply-chain attestation.

In [`parked.md`](parked.md), not scheduled at all: the agent model and reconciliation (ADR 017, ADR 029), multi-component applications (ADR 038) including any extension of `[run.workers]` to per-process environment, ports or limits, and the generator's system-closure output target (TR-03 §9.7).
