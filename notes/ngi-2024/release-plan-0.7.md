# Hop3 0.7.0 Release Plan — Final NGI Version

**Depends on:** 0.6.0 (2026-06-20).
**Status (2026-07-30):** the tree is on **0.7.0**; the tag and the PyPI publish are the last mechanical step of the week. Two items originally slated for the cut — the **email addon** (M3.1) and **nixpkgs pinning** (M1/M2) — shipped early in **0.6.1/0.6.2**. The intervening weeks went to platform-robustness / DX work not in the original scope but required for advertising a curated app set: ADR 052 CLI consistency, a failed-deploy observability overhaul, content-aware healthchecks (`[healthcheck].contains`), testlab hardening, the 2026-06 auth-audit remediation, and a nix-reliability pass (forgejo GC-root retention + a per-app nixpkgs pin). The **WAF (M3.5)** — the largest remaining 0.7 item — has since landed end-to-end: LeWAF **0.7.6** on PyPI, per-app `nginx → LeWAF → uWSGI` proxying, autonomous in-process L7 bans, and two Docker e2e proofs. The **2026-07 security remediation** (five defects, `local-notes/plans/28-security-remediation.md`) is **closed**, so the tag gate is now Web UI + screencasts + a recorded all-green catalog run + release mechanics.

0.7 is the final NGI deliverable release. This plan tracks **what is left** — first to tag 0.7.0, then to complete NGI in near-term 0.7.x point releases. It does not pretend the ~40 person-days remaining fit in one week; it separates the tag gate from the 0.7.x tail.

## Milestone status (annex T1–T5)

Every annex milestone accounted for, so a reviewer can reconcile the whole project plan (#2024-04-365).

| Task | Milestone | Status | Lands in |
|------|-----------|--------|----------|
| **T1** Nix builders | M1.1 Native Nix builder | ✅ | 0.5; pin 0.6.1; hermetic → 0.7.x |
| | M1.2 Template builders (Py/Node/Ruby/Go/Rust/Java) | ✅ | 0.5 |
| **T2** Nix runtime | M2.1 Spec & PoC | ✅ | 0.5 |
| | M2.2 Beta implementation | ✅ | **0.7** — beta done (contract + gate + hardening code); 1.0 → M2.3 |
| | M2.3 Final "1.0" | ○ | 0.7.x / 0.8 |
| **T3** Security & resilience | M3.1 Backing services (email) | ✅ | **0.7** — email = swappable-backend addon; **relay + catch** supported (catch e2e green), loopback endpoint, cert+deploy notifications, WordPress SMTP; **direct** ships as preview; per-app override / sub-creds / SES / encryption → **0.8+** (`22-email-roadmap-0.8-plus.md`) |
| | M3.2 Upgrades + migrations | ✅ | **0.7** — server-verify + app upgrade/rollback shipped; `upgrade-chain` e2e green on Docker + Hetzner (`--to` source-fetch + Web UI → 0.7.x) |
| | M3.3 Backups + migration tests | ✅ | 0.6 |
| | M3.4 Testing framework + canary | ✅ | shipped |
| | M3.5 Firewalls + WAF | ✅ | **0.7** — L3/L4 firewall + L7 WAF (LeWAF/OWASP-CRS) shipped end-to-end |
| | M3.6 CLI | ✅ | 0.5–0.6 |
| | M3.7 Web UI | ◐ | **0.7** — basic/clean/usable |
| | M3.8 Security audit + a11y | ◐ | **0.7** — three audit rounds processed in-house + security model published; a11y → 0.7.x; third-party review applied for, never allocated |
| **T4** Packaged apps | M4.1–4.4 (20 apps + reports) | ◐ | 0.7.x |
| **T5** Dissemination | M5.1 Website/blog | ✅ | shipped (23 posts) |
| | M5.2 Documentation | ✅ | 0.6 |
| | M5.3 Technical report / paper | ◐ | 0.7.x |
| | M5.4 Conference | ✅ | OW2Con / OSXP |
| | M5.6 Videos/screencasts | ◐ | **0.7** — 68 recorded; publish |

12 done, 7 partial, 1 not-started of the 20 named milestones (the annex skips M5.5).

## What's left for the 0.7 tag

### WAF / L7 firewall (M3.5) — ✅ complete
Network firewall + fixed-port registry shipped (ADR 045). The WAF (ADR 050, LeWAF — pure-Python OWASP-CRS) is complete end-to-end: LeWAF **0.7.6 released on PyPI**, the `hop3-server[waf]` engine installs by default, and a WAF-enabled app is fronted by `nginx → LeWAF proxy → uWSGI` on deploy.

- [x] LeWAF proxy lifecycle — per-app `lewaf-proxy` supervised as a uWSGI Emperor vassal (started on deploy, reaped on destroy); `hop3-server[waf]` extra, lazy import
- [x] nginx integration — app traffic routes through the WAF proxy (`app.waf_port`); activated on deploy, removed on destroy, the app stays loopback
- [x] L7 bans (detect → score → 403) per ADR 050 §4 — audit-stream scorer + `Ban` ORM + `hop3 waf bans` CLI, reconciled automatically in-process (`waf_bans_service`, ~60s)
- [x] OWASP Top 10 tests (SQLi / XSS / path-traversal / RCE) + a `skip-body-inspection` false-positive pass; a Docker e2e proves CRS blocking **and** the full ban loop over the real proxy chain
- [x] Documented `[waf]` + the WAF CLI in the config/CLI reference; ADR 050 marked shipped

### Web UI — basic, clean, usable (M3.7)
The dashboard exists (9 controllers, 21 templates, and it now installs from the signed catalog); make it clean and verify the core flows. Git-URL deploy, log streaming, a11y, and mobile are nice-to-haves that can ride to 0.7.x.

- [ ] Visual tidy-up: consistent layout, navigation, loading/empty/error states
- [ ] Verify core CRUD flows end to end from the UI (app list/status/logs, addons, backups, env)
- [ ] (if time) wire the disabled Git-URL deploy field; basic in-browser log streaming

### Security — audit rounds done in-house (M3.8)

Internal fixes shipped in 0.5–0.6. The third-party review was applied for and followed up twice with NLnet without an auditor ever being allocated; the milestone no longer waits on it. We audited the platform ourselves with tooling we found and partly built (`letscode` + the `vulnhunt` plugin) and processed the outcomes — the substitution is stated plainly in the report rather than glossed. If the review is still allocated later we will act on its findings.

- [x] One or two more internal audit rounds; fix findings
- [x] Applied for the third-party review; two follow-ups sent, no auditor allocated
- [x] Third audit round run in-house — `notes/security/report-2026-07.md`
- [x] Document the security model — published as `guides/security.md` (operators) and `developers/security-model.md` (developers/auditors), with `notes/security/security-model.md` as the engineering source
- [x] Fix the five open defects from the 2026-07 round (`local-notes/plans/28-security-remediation.md`) — **done 2026-07-29**: `run_as_hop3` argv split (16 argv / 4 shell call sites), addon restore-path containment, a fail-loud multi-worker/in-memory-rate-limiter invariant, the `user add` single-tenancy notice, and documented host-key pinning. Each landed with a regression test asserting the rejection; `make lint` and `make test-fast` green.
- [ ] Publish the July round as a blog post (the third-party review never allocated → we built tooling and audited ourselves) — counts toward M5.1

### Upgrade mechanism (M3.2)
Hop3-server's own Alembic migrations work. Scope confirmed (`local-notes/specs/upgrades.md`): the server upgrade is the installer/deployer's job (and ultimately the `hop3-server` command), **not** a `hop3` client command — there is no `hop3 server upgrade` RPC and no in-product self-upgrade.

- [x] Server upgrade defined, documented, and made fail-loud: after installing new code and migrating, the deployer verifies hop3-server actually answers before reporting "complete" — on failure it prints the exact command to revert to the previous release (plus the pre-upgrade-DB-restore caveat) instead of leaving a silently dead server. Admin guide gained an "Upgrading Hop3" section.
- [x] App-level upgrade orchestration: `hop3 app upgrade --app <app>` snapshots → redeploys + runs the app's `before-run` migrations → health-verifies → auto-rolls-back to the pre-upgrade snapshot on any failure.
- [x] Rollback-on-failure + operator-driven rollback: `hop3 app rollback --app <app> [--to <backup-id>]` (default: most recent, app-scoped; a foreign backup id is refused).
- [x] Deploy service ops are process-manager-aware and fail loud: restart + nginx reload pick the right mechanism per target (systemd on real servers, `supervisorctl` / `nginx -s reload` under supervisor) — the Docker restart was a silent `systemctl` no-op that kept serving old code while reporting success; the admin-domain/SSL nginx setup now fails the deploy on a reload failure instead of warning-and-continuing; and the installer degrades gracefully (rather than crashing) on a host with neither systemd nor supervisor.
- [x] Installer e2e made runnable and hermetic: the `hop3-installer` `c_e2e` suite (dark since the `--import-mode=importlib` switch) is fixed and folded into `make test-e2e`, and a stray `HOP3_DEV_HOST` in the shell can no longer make a test deploy to a real host.
- [x] Docker deploys can upgrade in place: the docker deploy backend now honours `--clean` (reuses a running container instead of recreating it every deploy), so a second `hop3-deploy-server --docker` hits the update path rather than a fresh install — the prerequisite for testing upgrades without an external host.
- [x] Cross-version upgrade e2e — `hop3-test upgrade-chain`, **green on both a Docker container and a fresh Hetzner VPS**: install a baseline release on a fresh box, then upgrade in-place through a version chain, asserting each hop deploys, the server answers, and the schema is readable. Each version is installed by **its own** installer (git worktree per tag → `uv run hop3-deploy-server`), so it tests the real upgrade path, not the current-installer-with-old-binaries pairing. Documented (ADR 043 §10, testing docs). The default chain starts at `0.6.2` — `hop3-rootd 0.6.0` is a broken baseline (can't start).
- [ ] App-upgrade `--to <git-ref|version>` source-fetch (→ 0.7.x); today `upgrade` is the safe redeploy of current source that a plain deploy lacks. Web UI rollback also → 0.7.x (CLI first).

### Screencasts — publish (M5.6)
68 asciicasts recorded (33 demos + 35 tutorials, each a real run).

- [ ] Review pass over the 68
- [ ] Upload to asciinema.org; capture the URLs for the NGI report
- [ ] Publish to the website + PeerTube; embed in the getting-started docs
- [ ] (optional) the two narrated walkthroughs — "Zero to Running App" and "Dashboard Tour"

### One recorded all-green catalog run (M4 evidence)

The 2026-07-27/28 campaign left every one of the 20 catalog apps seen green, but **no single recorded run is 20/20** — the best complete recording is 19/20. The report and the results-links doc both cite this number, so it is a tag-gate artefact, not a nicety.

- [ ] Re-baseline first. On 2026-07-29 a one-line regression in the shared check helper (`Check._request` gained a named `data` parameter and stopped forwarding it, so every form POST sent an empty body) failed 18/20 at once and prompted edits to four recipes that had been passing. The helper is fixed with a mutation-verified test (`test_request_carries_data.py`) and the four recipes reverted; **the state of the corpus is therefore unverified until a clean run**, and no per-app diagnosis should be trusted before one.
- [ ] Then run `./scripts/check-catalog.py` against a `hop3-deploy-server --provider hetzner --clean` rebuild, save the log, and work only from its output. Two apps carry an open question into that run: **uptime-kuma** (had a passing login at 13:26 on 2026-07-29, then refused the credential — the probe-account gating change is the suspect) and **isso** (405 on the login POST, unexplained).

### Release mechanics
- [ ] Finish the `[0.7.0]` changelog entry (started in `CHANGES.md`)
- [ ] Bump to 0.7.0; tag v0.7.0
- [ ] Blog post: "Hop3 0.7"

## What's left for 0.7.x (NGI complete)

### Benchmarks + final paper (M5.3) — the longest chain

Measured, not pending. Everything runs through `hop3-bench` and lands as tracked JSONL in `notes/benchmarks/`; nothing in the paper is hand-typed.

- [x] Baseline — K3s measured like-for-like: **7.8× heavier** (1441 vs 185 MB)
- [x] B1 control-plane memory + B3 closure-vs-image + update-delta + reproducibility — the read-only tier, re-run 2026-07-28 (`2026-07-28-readonly.jsonl`)
- [x] B2 deploy latency by build strategy — the 80-cell matrix, re-run 2026-07-28 (`2026-07-28-matrix.jsonl`, **71/80 ok**, 6 no-recipe, 3 failed). Median deploy 98 s native / 110 s nix / 116 s nix-gen / 163 s docker: the Nix paths land within 12–18% of native and are 1.4–1.5× faster than Docker.
- [x] B5 bit-for-bit reproducibility — **30/30** nix-gen recipes, the one benchmark that measures the headline claim instead of asserting it
- [x] Fresh-box control-plane memory (`2026-07-28-freshbox-memory.jsonl`) — settles the cgroup-vs-PSS problem: `memory.current` swings ~8× on page cache, PSS is stable, so the paper reports PSS
- [ ] **N≥3 repeats with variance.** Every cell is still n=1, so the paper says "preliminary". This is the single biggest remaining threat to the evaluation.
- [ ] Isolate the variant-ordering effect — all four variants ran sequentially on one box, so later variants inherit warmer caches
- [ ] Pre-registration: commit the protocol with empty result skeletons *before* the repeat run, so "pre-registered" is true rather than aspirational
- [ ] Fold the numbers into the paper's §6.3/§6.4; final prose pass; venue; submit; archive on HAL

### Nix runtime 1.0 (M2.3)
- [ ] The 20-app runtime pass + formal per-app dispositions (fix / defer-upstream / drop)
- [ ] `make test-nix` in the nightly Test Lab with a persisted `/nix/store`
- [ ] `[nix]` reference polish + reproducibility tiers; the 1.0 cut

### Full Nix reproducibility — hermetic builds (M1/M2)
Pinning (0.6.1) removed the moving-channel problem; hermeticity is the rest.

- [ ] Hermetic dependency builds for the flagship apps (uv2nix / composer2nix / pnpm `fetchDeps`); where infeasible, lock the dep set and label an explicit non-hermetic tier
- [ ] Fail loud on floating deps — templates refuse to generate on unversioned language deps
- [ ] Reproducibility CI gate: rebuild 2× (ideally on a 2nd arch), assert identical store paths for the pure-Nix tier
- [ ] `nix build` / flakes for a lock-pinned input set; declare substituters / trusted keys
- [ ] Update ADR 008 tiers + per-app labels (incl. aarch64)

### Packaged apps — final pass + production validation (M4)
20+ apps configured and tested across four variants; 20 experience reports (Draft).

- [x] **Manual test / cleanup pass over the 20+ apps — done 2026-07-28, and it is now an automated gate.** All 20 catalog apps were installed one at a time through the Web UI and every failure fixed as a platform class (23 commits). The pass ends with **all 20 installing from the signed catalog and accepting a real login on a pristine server**. (Precisely: the most recent complete recorded run returned 19/20, the twentieth failing on catalog content that predated its own fix rather than on a defect, and passing once republished. Every application has been seen green; a single all-green recorded run is outstanding and is not rounded up to here.) It is reproducible rather than anecdotal: `hop3-catalog/scripts/check-catalog.py` runs list → install → login-check → destroy and exits non-zero on any failure, against a `hop3-deploy-server --provider hetzner --clean` rebuild. Each app ships a `check.py` (required to publish) that signs in through the app's own auth surface and confirms a wrong password is refused; the check runs at the end of **every** deploy, Web UI included. Apps may declare a `[probe]` account — Hop3-owned, non-privileged, password rotated by Hop3 — so the check keeps working after an operator changes the admin password.
- [ ] Fix the apps still red on the nix suite (all app-level, not runtime): **easy-appointments** + **wordpress** (config file — `config.php` / `wp-config.php` — not created at runtime; identical across native + nix, so an app-setup / before-run-config-write issue); **nextcloud** (`/status.php` never ready); **forgejo** (180 s health-check timeout — and while there, confirm whether the M2.2 closure pre-flight fired: `sudo -u hop3 which nix-store` on the box; if absent, harden the pre-flight to resolve `nix-store` absolutely); **etherpad** (fill the placeholder nixos-25.05 rev + `nix-prefetch-url` hash).
- [ ] **The 20 experience reports — the other half of M4, and the weakest artefact in the set.** Reviewed 2026-07-28 (`local-notes/plans/27-experience-reports.md`); no edits applied yet. Three problems, in descending order of severity: (a) they assert a definition of "working" the project has since rejected — a reviewer who reads them after §6.1 of the report sees the contradiction; (b) the list is wrong — reports and catalog overlap on only 15, so **5 must be written** (bugsink, forgejo, keycloak, paheko, uptime-kuma) and **5 retired or re-scoped** (adminer, focalboard — dropped from the corpus entirely — grafana, jenkins, wiki-js); (c) the implicit template is too thin. Agreed shape: machine-checked YAML frontmatter on every report (`hop3-tools catalog reports`), the approved `TEMPLATE.md`, two screenshots per app (login page + signed-in default page, generated by `shoot-catalog.py` into `notes/experience-reports/images/`), and a single bundled PDF.
- [ ] Production deploys with real traffic
- [ ] Application gallery page on hop3.cloud

### Accessibility scan (M3.8)
- [ ] Accessibility scan (with the M3.7 polish)
- [ ] If NLnet allocates a third-party reviewer after all: run it, address feedback (not a blocker — see the M3.8 section above)

### Email addon refinements (M3.1)
Email is a **backing service with a swappable backend**, symmetric with the database addon (ADR 054): the operator picks a backend once at the server level, an app opts in by attaching an email addon (and then inherits that backend), and the app-facing contract (`SMTP_*`/`EMAIL_*`/`MAIL_*`/`SMTP_URL`, all pointing at a loopback SMTP endpoint) is stable across backends. 0.6.1 shipped the interface; the work left is the backends and the productization.

**The 0.7 cut** (details + backlog: `local-notes/plans/20-email-0.7-features.md`; 0.8+ roadmap: `22-email-roadmap-0.8-plus.md`):

*Ships in 0.7 — supported (experimental):*
- [x] `server email backend <kind>` verb (`server email set` = the `relay` alias) + the loopback `127.0.0.1:25` endpoint, opt-in per app, `--with email` (Postfix), pm-aware reload
- [x] **relay** backend — provider/corporate smarthost; provider profiles (Resend/Postmark/Brevo/Mailgun/Mailgun-EU/Scaleway TEM, EU-first) + DKIM auto-verify; deliverability pre-flight (never-fake)
- [x] **catch** backend — dev sink, **e2e-validated**
- [x] **Notifications** — cert-renewal + deploy-failure through the active backend
- [x] **WordPress (native)** SMTP via a self-guarding mu-plugin; docs

*Ships in 0.7 as preview (code lands, not advertised as supported):*
- [~] **direct** backend — built and fails loud where it can't run (needs systemd + unblocked port 25); no e2e / supervisor gap / fresh-IP reputation caveats → full support in **0.8**

*Deferred to 0.8+ (no 0.7 functionality lost):*
- [ ] Per-app override via the loopback (own-`--smtp-*` still works direct-to-provider); rootd sender-map ops (7a) land dormant/unwired
- [ ] Sub-credentials (blocked on a provider API), SES/real-logic providers, outage/health notifications, encryption-at-rest + atomic writes; relay/direct e2e; other WordPress variants

### Migration series (T5)
- [ ] Publish the 21 drafted "migrating from X" posts — drafts sit in `local-notes/blog/migrating-from-*.md`; one (Heroku) is published, so the pattern is proven and the rest is a review-and-move pass

### Final NGI report
- [ ] `notes/ngi-2024/results-links-2026-07.md` — the per-milestone evidence doc the auditors read. Still marked draft and dated "XX July 2026"; refreshed 2026-07-30 but needs the post-tag links (v0.7.0 release, asciinema URLs, gallery page, the reports PDF) and a submission date.
- [ ] The report itself (`notes/reports/draft-paper.md` §10 reconciles annex T1–T5) — once the above are complete.

## Out of scope (post-NGI)

Agent model (ADR 017), SSO / identity management, a monitoring / metrics dashboard, and multi-server / distributed deployment (JumpGATE).

## Risks

| Risk | Mitigation |
|------|------------|
| WAF (the big 0.7 item) overruns the cut week — **resolved**: shipped end-to-end (LeWAF 0.7.6, in-process bans, Docker e2e) | Conservative default ruleset; per-app tuning available; the kernel-level (L3/L4) ban upgrade is deferred to a later ADR |
| Benchmarks show Hop3 slower than a baseline | Report accurately — the contribution is architecture + reproducibility, not raw speed |
| External review surfaces issues late | Internal rounds first; address findings in 0.7.x |
| Production deploys uncover blocker bugs | Triage: fix critical, defer the rest with notes |
| Reproducibility questioned at review | Pinning (0.6.1) closed the worst gap; ADR 008 documents the tiers; hermetic + CI gate land in 0.7.x |
