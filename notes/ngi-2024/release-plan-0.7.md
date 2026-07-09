# Hop3 0.7.0 Release Plan — Final NGI Version

**Depends on:** 0.6.0 (2026-06-20).
**Status (2026-07-09):** the tree is on **0.6.2**; **0.7.0 is not yet tagged**. Two items originally slated for the cut — the **email addon** (M3.1) and **nixpkgs pinning** (M1/M2) — shipped early in **0.6.1/0.6.2**. The intervening weeks went to platform-robustness / DX work not in the original scope but load-bearing for advertising a curated app set: ADR 052 CLI consistency, a failed-deploy observability overhaul, content-aware healthchecks (`[healthcheck].contains`), testlab hardening, the 2026-06 auth-audit remediation, and a nix-reliability pass (forgejo GC-root retention + a per-app nixpkgs pin). The **WAF (M3.5)** — the largest remaining 0.7 item — has since landed end-to-end: LeWAF **0.7.6** on PyPI, per-app `nginx → LeWAF → uWSGI` proxying, autonomous in-process L7 bans, and two Docker e2e proofs.

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
| | M3.8 Security audit + a11y | ◐ | **0.7** internal; external → 0.7.x |
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
The dashboard exists (9 controllers, 17 templates); make it clean and verify the core flows. Git-URL deploy, log streaming, a11y, and mobile are nice-to-haves that can ride to 0.7.x.

- [ ] Visual tidy-up: consistent layout, navigation, loading/empty/error states
- [ ] Verify core CRUD flows end to end from the UI (app list/status/logs, addons, backups, env)
- [ ] (if time) wire the disabled Git-URL deploy field; basic in-browser log streaming

### Security — internal rounds, engage the firm (M3.8)
Internal fixes shipped in 0.5–0.6; the external review is 0.7.x.

- [ ] One or two more internal audit rounds; fix findings
- [ ] Engage the external security-audit firm
- [ ] Document the security model in the admin guide

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

### Release mechanics
- [ ] Finish the `[0.7.0]` changelog entry (started in `CHANGES.md`)
- [ ] Bump to 0.7.0; tag v0.7.0
- [ ] Blog post: "Hop3 0.7"

## What's left for 0.7.x (NGI complete)

### Benchmarks + final paper (M5.3) — the longest chain (~8–9 days)
- [ ] Baseline (Dokku + K3s, or Docker Compose + bare uWSGI)
- [ ] B1 control-plane memory (0/10/28 apps); B2 deploy latency by build strategy; B3 Nix closure vs Docker image size; B4 cold-start; B5 bit-for-bit reproducibility
- [ ] Integrate into the paper's evaluation; submit; archive on HAL

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

- [ ] Manual test / cleanup pass over the 20+ apps
- [ ] Fix the apps still red on the nix suite (all app-level, not runtime): **easy-appointments** + **wordpress** (config file — `config.php` / `wp-config.php` — not created at runtime; identical across native + nix, so an app-setup / before-run-config-write issue); **nextcloud** (`/status.php` never ready); **forgejo** (180 s health-check timeout — and while there, confirm whether the M2.2 closure pre-flight fired: `sudo -u hop3 which nix-store` on the box; if absent, harden the pre-flight to resolve `nix-store` absolutely); **etherpad** (fill the placeholder nixos-25.05 rev + `nix-prefetch-url` hash).
- [ ] Production deploys with real traffic; finalise the experience reports
- [ ] Application gallery page on hop3.cloud

### External security review (M3.8)
- [ ] The external firm's review; address feedback
- [ ] Accessibility scan (with the M3.7 polish)

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
- [ ] Publish the 21 drafted "migrating from X" posts

### Final NGI report
- [ ] Once the above are complete.

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
