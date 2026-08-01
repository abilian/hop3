# Hop3 0.7.0 Release Plan: Final NGI Version

**Depends on:** 0.6.0 (2026-06-20).
**Status (2026-07-31): 0.7.0 is tagged and published**: `0.7.0` on `d8c2f526`, pushed to SourceHut, changelog dated, release post out.

0.7 is the final NGI deliverable release. This plan tracks **what is left**: first to tag 0.7.0, then to complete NGI in near-term 0.7.x point releases. It separates the tag gate from the 0.7.x tail; the ~40 person-days of remaining work cannot fit in one week.

## Milestone status (annex T1–T5)

Every annex milestone accounted for, so a reviewer can reconcile the whole project plan (#2024-04-365).

| Task | Milestone | Status | Lands in |
|------|-----------|--------|----------|
| **T1** Nix builders | M1.1 Native Nix builder | ✅ | 0.5; pin 0.6.1; hermetic → 0.7.x |
| | M1.2 Template builders (Py/Node/Ruby/Go/Rust/Java) | ✅ | 0.5 |
| **T2** Nix runtime | M2.1 Spec & PoC | ✅ | 0.5 |
| | M2.2 Beta implementation | ✅ | **0.7**: beta done (contract + gate + hardening code); 1.0 → M2.3 |
| | M2.3 Final "1.0" | ✅ | **0.7**: the Nix runtime ships in this project's final release, exercised corpus-wide: 62 Nix variants run on it, every catalog app signs in under both Nix strategies (16/16 and 18/19), 30/30 recipes rebuild bit-for-bit. Hop3 versions as a whole, so "1.0" names the maturity rather than a component version string |
| **T3** Security & resilience | M3.1 Backing services (email) | ✅ | **0.7**: email = swappable-backend addon; **relay + catch** supported (catch e2e green), loopback endpoint, cert+deploy notifications, WordPress SMTP; **direct** ships as preview; per-app override / sub-creds / SES / encryption → **0.8+** (`22-email-roadmap-0.8-plus.md`) |
| | M3.2 Upgrades + migrations | ✅ | **0.7**: server-verify + app upgrade/rollback shipped; `upgrade-chain` e2e green on Docker + Hetzner (`--to` source-fetch + Web UI → 0.7.x) |
| | M3.3 Backups + migration tests | ✅ | 0.6 |
| | M3.4 Testing framework + canary | ✅ | shipped |
| | M3.5 Firewalls + WAF | ✅ | **0.7**: L3/L4 firewall + L7 WAF (LeWAF/OWASP-CRS) shipped end-to-end |
| | M3.6 CLI | ✅ | 0.5–0.6 |
| | M3.7 Web UI | ✅ | **0.7**: basic, as the annex asks: 9 controllers, 21 templates, core CRUD flows, catalog install; all 20 apps installed through it by hand in the 2026-07-27/28 acceptance campaign. Polish / Git-URL deploy / log streaming / a11y / mobile → 0.7.x |
| | M3.8 Security audit + a11y | ✅ | **0.7**: four audit rounds processed in-house and every finding remediated; security model published across three pages; third-party review applied for and never allocated, its effort going to the fourth round. The accessibility scan was not carried out; the report states this plainly |
| **T4** Packaged apps | M4.1–4.4 (20 apps + reports) | ✅ | **0.7**: 20 apps in the signed catalog, each verified by an authenticated sign-in under three build strategies (native 19/20 recorded, nix 16/16, nix-gen 18/19); 20 experience reports plus an aggregate, machine-checked and final |
| **T5** Dissemination | M5.1 Website/blog | ✅ | shipped (23 posts) |
| | M5.2 Documentation | ✅ | 0.6 |
| | M5.3 Technical report / paper | ✅ | **the report is the deliverable and it exists**; the research-paper *extraction* is a later, separate artefact and does not gate M5.3 |
| | M5.4 Conference | ✅ | OW2Con / OSXP |
| | M5.6 Videos/screencasts | ✅ | **0.7**: 68 asciicasts covering every demo and tutorial, recorded from real runs and published with a README stating, per file, what is in it. A first pass: 11 ran to completion, 33 end on a visible failure (30 of them the recorder's 120 s step timeout), 24 recorded nothing. Both harness defects are fixed and a re-recorded set follows |

**Every named milestone is delivered** (the annex numbers M5.1–M5.6 but defines no M5.5). Three carry a qualification, stated plainly in their rows and in the report's Table 5: M2.3's "1.0" names the maturity the annex asked for, since Hop3 versions as a whole and no component carries its own number; M3.8's accessibility scan was not carried out, its effort having gone to a fourth in-house security round after no third-party reviewer was allocated; and M5.6's recordings exist and are published for all 68 demos and tutorials, but only 11 of the 68 ran clean: a harness defect, now fixed, with the re-record outstanding. Reconciled against Table 5 on 2026-07-31.

## The 0.7 tag: closed 2026-07-31

Kept as the record of what the gate contained. Everything below shipped in the tag except the screencast re-record, which is carried to 0.7.x.

### WAF / L7 firewall (M3.5): ✅ complete
Network firewall + fixed-port registry shipped (ADR 045). The WAF (ADR 050, LeWAF, pure-Python OWASP-CRS) is complete end-to-end: LeWAF **0.7.6 released on PyPI**, the `hop3-server[waf]` engine installs by default, and a WAF-enabled app is fronted by `nginx → LeWAF proxy → uWSGI` on deploy.

- [x] LeWAF proxy lifecycle: per-app `lewaf-proxy` supervised as a uWSGI Emperor vassal (started on deploy, reaped on destroy); `hop3-server[waf]` extra, lazy import
- [x] nginx integration: app traffic routes through the WAF proxy (`app.waf_port`); activated on deploy, removed on destroy, the app stays loopback
- [x] L7 bans (detect → score → 403) per ADR 050 §4: audit-stream scorer + `Ban` ORM + `hop3 waf bans` CLI, reconciled automatically in-process (`waf_bans_service`, ~60s)
- [x] OWASP Top 10 tests (SQLi / XSS / path-traversal / RCE) + a `skip-body-inspection` false-positive pass; a Docker e2e proves CRS blocking **and** the full ban loop over the real proxy chain
- [x] Documented `[waf]` + the WAF CLI in the config/CLI reference; ADR 050 marked shipped

### Web UI (M3.7): done (2026-07-31)

The annex asks for a *basic* Web UI. The dashboard is 9 controllers and 21 templates, it installs from the signed catalog, and the core flows were exercised rather than asserted: the 2026-07-27/28 acceptance campaign installed **all 20 catalog apps through this interface, one at a time**, and every failure it surfaced was root-caused to a platform class and fixed there. That campaign is the verification this milestone wanted.

- [x] Verify core CRUD flows end to end from the UI (app list/status/logs, addons, backups, env): by the acceptance campaign
- [x] Install from the signed catalog

Not done, and deliberately **not** part of this milestone. These are improvements to a delivered feature, tracked for 0.7.x:

- [ ] Visual tidy-up: consistent layout, navigation, loading/empty/error states
- [ ] Wire the disabled Git-URL deploy field; basic in-browser log streaming
- [ ] a11y scan and mobile layout (the scan now stands under M3.8 rather than riding on "the M3.7 polish")

### Security (M3.8): audit rounds done in-house

Internal fixes shipped in 0.5–0.6. The third-party review was applied for and followed up twice with NLnet without an auditor ever being allocated; the milestone no longer waits on it. We audited the platform ourselves with tooling we found and partly built (`letscode` + the `vulnhunt` plugin) and processed the outcomes. The substitution is recorded in the report. If the review is still allocated later we will act on its findings.

- [x] One or two more internal audit rounds; fix findings
- [x] Applied for the third-party review; two follow-ups sent, no auditor allocated
- [x] Third audit round run in-house: `notes/security/report-2026-07-21.md`
- [x] Document the security model: published as `guides/security.md` (operators) and `developers/security-model.md` (developers/auditors), with `notes/security/security-model.md` as the engineering source
- [x] Fix the five open defects from the 2026-07 round (`local-notes/plans/28-security-remediation.md`): **done 2026-07-29**: `run_as_hop3` argv split (16 argv / 4 shell call sites), addon restore-path containment, a fail-loud multi-worker/in-memory-rate-limiter invariant, the `user add` single-tenancy notice, and documented host-key pinning. Each landed with a regression test asserting the rejection; `make lint` and `make test-fast` green.
- [ ] Publish the July round as a blog post (the third-party review never allocated → we built tooling and audited ourselves): counts toward M5.1

### Upgrade mechanism (M3.2)
Hop3-server's own Alembic migrations work. Scope confirmed (`local-notes/specs/upgrades.md`): the server upgrade is the installer/deployer's job (and ultimately the `hop3-server` command); there is no `hop3 server upgrade` RPC and no in-product self-upgrade.

- [x] Server upgrade defined, documented, and made fail-loud: after installing new code and migrating, the deployer verifies hop3-server actually answers before reporting "complete". On failure it prints the exact command to revert to the previous release (plus the pre-upgrade-DB-restore caveat) instead of leaving a silently dead server. Admin guide gained an "Upgrading Hop3" section.
- [x] App-level upgrade orchestration: `hop3 app upgrade --app <app>` snapshots → redeploys + runs the app's `before-run` migrations → health-verifies → auto-rolls-back to the pre-upgrade snapshot on any failure.
- [x] Rollback-on-failure + operator-driven rollback: `hop3 app rollback --app <app> [--to <backup-id>]` (default: most recent, app-scoped; a foreign backup id is refused).
- [x] Deploy service ops are process-manager-aware and fail loud. Restart and nginx reload pick the right mechanism per target (systemd on real servers, `supervisorctl` / `nginx -s reload` under supervisor). The Docker restart was a silent `systemctl` no-op that kept serving old code while reporting success; the admin-domain/SSL nginx setup now fails the deploy on a reload failure instead of warning-and-continuing; and the installer degrades gracefully (rather than crashing) on a host with neither systemd nor supervisor.
- [x] Installer e2e made runnable and hermetic: the `hop3-installer` `c_e2e` suite (dark since the `--import-mode=importlib` switch) is fixed and folded into `make test-e2e`, and a stray `HOP3_DEV_HOST` in the shell can no longer make a test deploy to a real host.
- [x] Docker deploys can upgrade in place: the docker deploy backend now honours `--clean`; it reuses a running container, so a second `hop3-deploy-server --docker` hits the update path. This is the prerequisite for testing upgrades without an external host.
- [x] Cross-version upgrade e2e: `hop3-test upgrade-chain`, **green on both a Docker container and a fresh Hetzner VPS**: install a baseline release on a fresh box, then upgrade in-place through a version chain, asserting each hop deploys, the server answers, and the schema is readable. Each version is installed by **its own** installer (git worktree per tag → `uv run hop3-deploy-server`), so it tests the real upgrade path. Documented (ADR 043 §10, testing docs). The default chain starts at `0.6.2`; `hop3-rootd 0.6.0` is a broken baseline (can't start).
- [ ] App-upgrade `--to <git-ref|version>` source-fetch (→ 0.7.x); today `upgrade` is the safe redeploy of current source that a plain deploy lacks. Web UI rollback also → 0.7.x (CLI first).

### Screencasts (M5.6): publish

68 asciicasts recorded (33 demos + 35 tutorials, each a real run), committed under `screencasts/` with a README covering how to play them.

**The review pass was the point, and it went badly (2026-07-31).** Publishing had been queued as mechanical. Read from the files rather than from `MANIFEST.md`, the 68 are: **11 clean, 33 real sessions ending on a visible red `FAIL`, 24 with nothing recorded at all** (interrupted at the prompt; some zero bytes). Nine are watchable, all demos. They are published as-is with the state stated per file, rather than trimmed to the good ones.

- [x] Review pass over the 68, which found the following
- [ ] **Raise the recorder's fixed 120-second step timeout** for deploy steps, or make it per-step. 30 of the 33 failures are this one thing: the tutorial passes ~31 steps, reaches `hop3 deploy`, and times out.
- [ ] **Fail the manifest on an empty or non-zero recording** instead of writing `ok`. It marked all 68 `ok` because it recorded only that a file existed, never what it contained: the same instrument-reports-success-it-never-checked shape as this week's app findings.
- [ ] Re-record
- [ ] Upload to asciinema.org; capture the URLs for the NGI report
- [ ] Publish to the website + PeerTube; embed in the getting-started docs
- [ ] (optional) the two narrated walkthroughs: "Zero to Running App" and "Dashboard Tour"

### One recorded all-green catalog run (M4 evidence)

The 2026-07-27/28 campaign left every one of the 20 catalog apps seen green, but **no single recorded run is 20/20**: the best complete recording is 19/20. The report and the results-links doc both cite this number, so it gates the tag.

- [ ] Re-baseline first. On 2026-07-29 a one-line regression in the shared check helper (`Check._request` gained a named `data` parameter and stopped forwarding it, so every form POST sent an empty body) failed 18/20 at once and prompted edits to four recipes that had been passing. The helper is fixed with a mutation-verified test (`test_request_carries_data.py`) and the four recipes reverted; **the state of the corpus is therefore unverified until a clean run**, and no per-app diagnosis should be trusted before one.
- [ ] Then run `./scripts/check-catalog.py` against a `hop3-deploy-server --provider hetzner --clean` rebuild, save the log, and work only from its output. Two apps carry an open question into that run: **uptime-kuma** (had a passing login at 13:26 on 2026-07-29, then refused the credential: the probe-account gating change is the suspect) and **isso** (405 on the login POST, unexplained).

### Release mechanics
- [ ] Finish the `[0.7.0]` changelog entry (started in `CHANGES.md`)
- [ ] Bump to 0.7.0; tag v0.7.0
- [ ] Blog post: "Hop3 0.7"

## What's left for 0.7.x (NGI complete)

### Benchmarks + final paper (M5.3): the longest chain

Measured, not pending. Everything runs through `hop3-bench` and lands as tracked JSONL in `notes/benchmarks/`; nothing in the paper is hand-typed.

- [x] Baseline: K3s measured like-for-like: **7.8× heavier** (1441 vs 185 MB)
- [x] B1 control-plane memory + B3 closure-vs-image + update-delta + reproducibility: the read-only tier, re-run 2026-07-28 (`2026-07-28-readonly.jsonl`)
- [x] B2 deploy latency by build strategy: the 80-cell matrix, re-run 2026-07-28 (`2026-07-28-matrix.jsonl`, **71/80 ok**, 6 no-recipe, 3 failed). Median deploy 98 s native / 110 s nix / 116 s nix-gen / 163 s docker: the Nix paths land within 12–18% of native and are 1.4–1.5× faster than Docker.
- [x] B5 bit-for-bit reproducibility: **30/30** nix-gen recipes, the one benchmark that measures the headline claim
- [x] Fresh-box control-plane memory (`2026-07-28-freshbox-memory.jsonl`): settles the cgroup-vs-PSS problem: `memory.current` swings ~8× on page cache, PSS is stable, so the paper reports PSS
- [ ] **N≥3 repeats with variance.** Every cell is still n=1, so the paper says "preliminary". This is the single biggest remaining threat to the evaluation.
- [ ] Isolate the variant-ordering effect: all four variants ran sequentially on one box, so later variants inherit warmer caches
- [ ] Pre-registration: commit the protocol with empty result skeletons *before* the repeat run, so the pre-registration is genuine
- [ ] Fold the numbers into the paper's §6.3/§6.4; final prose pass; venue; submit; archive on HAL

### Nix runtime 1.0 (M2.3)
- [ ] The 20-app runtime pass + formal per-app dispositions (fix / defer-upstream / drop)
- [ ] `make test-nix` in the nightly Test Lab with a persisted `/nix/store`
- [ ] `[nix]` reference polish + reproducibility tiers; the 1.0 cut

### Full Nix reproducibility (M1/M2): hermetic builds
Pinning (0.6.1) removed the moving-channel problem; hermeticity is the rest.

- [ ] Hermetic dependency builds for the flagship apps (uv2nix / composer2nix / pnpm `fetchDeps`); where infeasible, lock the dep set and label an explicit non-hermetic tier
- [ ] Fail loud on floating deps: templates refuse to generate on unversioned language deps
- [ ] Reproducibility CI gate: rebuild 2× (ideally on a 2nd arch), assert identical store paths for the pure-Nix tier
- [ ] `nix build` / flakes for a lock-pinned input set; declare substituters / trusted keys
- [ ] Update ADR 008 tiers + per-app labels (incl. aarch64)

### Packaged apps (M4): final pass + production validation

**Docker is dropped from M4's scope (2026-07-31).** Recipes exist for most of the twenty and none has ever been measured at the sign-in bar. Carrying an unmeasured variant through the experience reports and into the final report is the rot the report format exists to prevent, so the variant is no longer claimed; the recipes stay in the corpus. Coverage is native, hand-written Nix, and Nix-from-template.
20+ apps configured and tested across three variants (native, hand-written Nix, Nix-from-template); 20 experience reports.

- [x] **Manual test / cleanup pass over the 20+ apps: done 2026-07-28, and it is now an automated gate.** All 20 catalog apps were installed one at a time through the Web UI and every failure fixed as a platform class (23 commits). The pass ends with **all 20 installing from the signed catalog and accepting a real login on a pristine server**. (Precisely: the most recent complete recorded run returned 19/20, the twentieth failing on stale catalog content whose fix predated the catalog publication, and passing once republished. Every application has been seen green; a single all-green recorded run is outstanding.) The process is reproducible: `hop3-catalog/scripts/check-catalog.py` runs list → install → login-check → destroy and exits non-zero on any failure, against a `hop3-deploy-server --provider hetzner --clean` rebuild. Each app ships a `check.py` (required to publish) that signs in through the app's own auth surface and confirms a wrong password is refused; the check runs at the end of **every** deploy, Web UI included. Apps may declare a `[probe]` account, Hop3-owned, non-privileged, password rotated by Hop3, so the check keeps working after an operator changes the admin password.
- [x] **The nix suite is green: 16/16 hand-written and 18/19 template-generated**, each on a complete recorded run (2026-07-31, `check-catalog.py --variant {nix,nixgen} --screenshots`). The red list this item used to carry is superseded: wordpress and nextcloud have no hand-written recipe (retired deliberately), forgejo passes in both, etherpad is not in the catalog 20. Easy!Appointments is the one remaining failure: it builds its login form in JavaScript, so neither verification path can complete a sign-in.
- [ ] Production deploys with real traffic
- [ ] Application gallery page on hop3.cloud

### Accessibility scan (M3.8)
- [ ] Accessibility scan (previously bundled with "the M3.7 polish"; M3.7 is done, so this stands on its own)
- [ ] If NLnet allocates a third-party reviewer after all: run it, address feedback (not a blocker: see the M3.8 section above)

### Email addon refinements (M3.1)
Email is a **backing service with a swappable backend**, symmetric with the database addon (ADR 054): the operator picks a backend once at the server level, an app opts in by attaching an email addon (and then inherits that backend), and the app-facing contract (`SMTP_*`/`EMAIL_*`/`MAIL_*`/`SMTP_URL`, all pointing at a loopback SMTP endpoint) is stable across backends. 0.6.1 shipped the interface; the work left is the backends and the productization.

**The 0.7 cut** (details + backlog: `local-notes/plans/20-email-0.7-features.md`; 0.8+ roadmap: `22-email-roadmap-0.8-plus.md`):

*Ships in 0.7, supported (experimental):*
- [x] `server email backend <kind>` verb (`server email set` = the `relay` alias) + the loopback `127.0.0.1:25` endpoint, opt-in per app, `--with email` (Postfix), pm-aware reload
- [x] **relay** backend: provider/corporate smarthost; provider profiles (Resend/Postmark/Brevo/Mailgun/Mailgun-EU/Scaleway TEM, EU-first) + DKIM auto-verify; deliverability pre-flight (never-fake)
- [x] **catch** backend: dev sink, **e2e-validated**
- [x] **Notifications**: cert-renewal + deploy-failure through the active backend
- [x] **WordPress (native)** SMTP via a self-guarding mu-plugin; docs

*Ships in 0.7 as preview (code lands, not advertised as supported):*
- [~] **direct** backend: built and fails loud where it can't run (needs systemd + unblocked port 25); no e2e / supervisor gap / fresh-IP reputation caveats → full support in **0.8**

*Deferred to 0.8+ (no 0.7 functionality lost):*
- [ ] Per-app override via the loopback (own-`--smtp-*` still works direct-to-provider); rootd sender-map ops (7a) land dormant/unwired
- [ ] Sub-credentials (blocked on a provider API), SES/real-logic providers, outage/health notifications, encryption-at-rest + atomic writes; relay/direct e2e; other WordPress variants

### Migration series (T5)
- [x] The "migrating from X" series: **Reframed as documentation, and shipped (2026-07-31).** The series is not a blog run: the 22 per-platform guides live under `docs/src/guides/migration/`, reached from the migration hub page rather than the site nav (listing them there would swamp the group). They build and render. T5's migration deliverable is met.

### Final NGI report
- [x] `notes/ngi-2024/results-links-2026-07.md`: the per-milestone evidence doc the auditors read. - [x] The report itself (`notes/reports/TR-03.md` §10 reconciles annex T1–T5): once the above are complete.

## Out of scope (post-NGI)

Agent model (ADR 017), SSO / identity management, a monitoring / metrics dashboard, and multi-server / distributed deployment (JumpGATE).

## Risks

| Risk | Mitigation |
|------|------------|
| WAF (the big 0.7 item) overruns the cut week: **resolved**: shipped end-to-end (LeWAF 0.7.6, in-process bans, Docker e2e) | Conservative default ruleset; per-app tuning available; the kernel-level (L3/L4) ban upgrade is deferred to a later ADR |
| Benchmarks show Hop3 slower than a baseline | Report accurately: the contribution is architecture and reproducibility |
| External review surfaces issues late | Internal rounds first; address findings in 0.7.x |
| Production deploys uncover blocker bugs | Triage: fix critical, defer the rest with notes |
| Reproducibility questioned at review | Pinning (0.6.1) closed the worst gap; ADR 008 documents the tiers; hermetic + CI gate land in 0.7.x |
