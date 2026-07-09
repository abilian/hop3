# Hop3 0.7.0 Release Plan — Final NGI Version

**Depends on:** 0.6.0 (2026-06-20).
**Status (2026-07-06):** the tree is on **0.6.2**; **0.7.0 is not yet tagged**. Two items originally slated for the cut — the **email addon** (M3.1) and **nixpkgs pinning** (M1/M2) — shipped early in **0.6.1/0.6.2**. The intervening weeks went to platform-robustness / DX work not in the original scope but load-bearing for advertising a curated app set: ADR 052 CLI consistency, a failed-deploy observability overhaul, content-aware healthchecks (`[healthcheck].contains`), testlab hardening, the 2026-06 auth-audit remediation, and a nix-reliability pass (forgejo GC-root retention + a per-app nixpkgs pin).

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
| **T3** Security & resilience | M3.1 Backing services (email) | ◐ | 0.6.1 (experimental); refinements → 0.7.x |
| | M3.2 Upgrades + migrations | ◐ | **0.7** — scope to confirm |
| | M3.3 Backups + migration tests | ✅ | 0.6 |
| | M3.4 Testing framework + canary | ✅ | shipped |
| | M3.5 Firewalls + WAF | ◐ | **0.7** — proxy slice remains |
| | M3.6 CLI | ✅ | 0.5–0.6 |
| | M3.7 Web UI | ◐ | **0.7** — basic/clean/usable |
| | M3.8 Security audit + a11y | ◐ | **0.7** internal; external → 0.7.x |
| **T4** Packaged apps | M4.1–4.4 (20 apps + reports) | ◐ | 0.7.x |
| **T5** Dissemination | M5.1 Website/blog | ✅ | shipped (23 posts) |
| | M5.2 Documentation | ✅ | 0.6 |
| | M5.3 Technical report / paper | ◐ | 0.7.x |
| | M5.4 Conference | ✅ | OW2Con / OSXP |
| | M5.6 Videos/screencasts | ◐ | **0.7** — 68 recorded; publish |

10 done, 9 partial, 1 not-started of the 20 named milestones (the annex skips M5.5).

## What's left for the 0.7 tag

### WAF / L7 firewall (M3.5) — the largest item
Network firewall + fixed-port registry shipped (ADR 045). The WAF (ADR 050, LeWAF — pure-Python OWASP-CRS): the schema, declarative→SecLang compiler, engine plugin, and named networks are **merged**; the proxy-running slice remains.

- [ ] LeWAF proxy lifecycle — start/stop/reload `lewaf-proxy` (`hop3-server[waf]` extra, lazy import)
- [ ] nginx integration — route app traffic through the WAF proxy; activate on deploy, remove on destroy
- [ ] L7 bans (detect → score → 403) per ADR 050 §4
- [ ] OWASP Top 10 tests (SQLi / XSS / path-traversal minimum) + a false-positive / per-app-exemption pass
- [ ] Document `[waf]` in the admin guide

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

### Upgrade mechanism (M3.2) — confirm scope
Hop3-server's own Alembic migrations work. Beyond that:

- [ ] Production `hop3 server upgrade` (pull + migrate + restart; admin-only)
- [ ] App-level upgrade orchestration: back up data + code → run the app's upgrade script → roll back on error → operator-driven rollback from CLI / Web UI
- [ ] Rollback-on-failure + an admin-guide upgrade procedure

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
0.6.1 shipped the minimal experimental slice; the transport/identity model implies:

- [ ] Server-level shared transport (`hop3 server email …`) that per-app addons reference
- [ ] Named-provider profiles (Resend / Postmark / Brevo / Mailgun / SES / Scaleway TEM; EU-sovereign first-class)
- [ ] Local relay — a host Postfix null-client on `localhost:25` + sendmail, so WordPress / PHP `mail()` / cron work with zero injection
- [ ] Dev catcher (a Mailpit backend mode)
- [ ] Platform notifications — reuse the transport for cert / deploy / outage alerts
- [ ] Per-app sub-credentials for reputation isolation

### Migration series (T5)
- [ ] Publish the 21 drafted "migrating from X" posts

### Final NGI report
- [ ] Once the above are complete.

## Out of scope (post-NGI)

Agent model (ADR 017), SSO / identity management, a monitoring / metrics dashboard, and multi-server / distributed deployment (JumpGATE).

## Risks

| Risk | Mitigation |
|------|------------|
| WAF (the big 0.7 item) overruns the cut week | Conservative default ruleset; per-app tuning → 0.7.x; the WAF itself can slip to early 0.7.x |
| Benchmarks show Hop3 slower than a baseline | Report accurately — the contribution is architecture + reproducibility, not raw speed |
| External review surfaces issues late | Internal rounds first; address findings in 0.7.x |
| Production deploys uncover blocker bugs | Triage: fix critical, defer the rest with notes |
| Reproducibility questioned at review | Pinning (0.6.1) closed the worst gap; ADR 008 documents the tiers; hermetic + CI gate land in 0.7.x |
