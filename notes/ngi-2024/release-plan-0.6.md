# Hop3 0.6.0 Release Plan — Final NGI Version

**Target:** Early June 2026
**Theme:** Complete all NGI commitments
**Depends on:** 0.5.0 released
**Last updated:** 2026-04-22 — proposed CLI commands migrated from colon syntax (`hop3 server:upgrade`, `hop3 app:upgrade`) to space form per ADR 036.

## Goals

Version 0.6 is the final NGI deliverable release. Every milestone
from the project plan (#2024-04-365) must be either complete or have
a documented, justified deferral agreed with NGI reviewers.

## NGI Milestone Completion Matrix

After 0.5.0, the following milestones remain open:

| Milestone | 0.5 Status | 0.6 Target |
|-----------|-----------|------------|
| M2.2 Nix runtime beta | Stabilised | Done |
| M2.3 Nix runtime 1.0 | Not started | Done |
| M3.1 Backing services | + S3 addon | + email addon (if not in 0.5) |
| M3.2 Upgrades | Partial | `hop3 upgrade` |
| M3.3 Backup migration | Not tested | Automated test |
| M3.5 Firewalls/WAF | Not started | Done |
| M3.6 CLI | Working | DX refactor done |
| M3.7 Web UI | Reviewed | Polished, Git URL deploy |
| M3.8 Security audit | 4 code fixes done | External review complete |
| M4.1-4 Packaged apps | Reports started | All 20 reports, production traffic |
| M5.3 Paper — benchmarks | Not started | Done |
| M5.3 Paper — final | Interim report refreshed | Submitted and published |
| M5.6 Screencasts | Not started | 2 screencasts published |

## Scope

### Firewall / WAF integration (M3.5)

- [ ] Review LeWAF codebase (Coraza-based WAF)
- [ ] Design WAF plugin architecture (per-app enable/disable in
      `hop3.toml`, probably under `[security]`)
- [ ] Implement nginx integration module
- [ ] Test against OWASP Top 10 (SQLi, XSS, path traversal at minimum)
- [ ] Basic network firewall rules (ufw/nftables) for app isolation
- [ ] Document in admin guide

### Upgrade mechanism (M3.2)

- [ ] `hop3 server upgrade` command (pulls latest, runs migrations,
      restarts services)
- [ ] App-level `hop3 app upgrade --app <app>` (re-deploy from latest source)
- [ ] Rollback on failure (keep previous version)
- [ ] Document upgrade procedure for admins

### Backup migration test (M3.3)

- [ ] Automated test: backup on server A, restore on server B
- [ ] Add to `hop3-test` as a system test
- [ ] Document disaster recovery procedure

### Paper benchmarks (M5.3)

- [ ] Set up comparison server (Dokku + K3s)
- [ ] Benchmark 1: Control plane memory (0, 10, 28 apps)
- [ ] Benchmark 2: Deployment time (5 apps)
- [ ] Benchmark 3: Nix closure vs Docker image sizes
- [ ] Benchmark 4: Startup time
- [ ] Integrate into paper Section 6.2
- [ ] Submit paper

### Screencasts (M5.6)

- [ ] Write scripts for both screencasts (~1 page each)
- [ ] Set up clean dev VM, install Hop3 fresh, dry-run the demos
- [ ] Record "Zero to Running App in 5 Minutes" (asciinema for
      terminal, OBS for browser if needed)
- [ ] Record "Dashboard Tour" (browser screen recording)
- [ ] Edit, add captions, export, upload to website + PeerTube
- [ ] Update `docs/src/getting-started.md` to embed the videos

### Web UI polish (M3.7)

- [ ] Visual review with a designer or UX-aware developer
- [ ] Deploy from Git URL in web UI
- [ ] Real-time log streaming in browser
- [ ] Mobile-responsive layout check

### Security external review (M3.8)

- [ ] Address any feedback from external review
- [ ] Accessibility scan (a11y) and fix critical issues
- [ ] Document security model in admin guide

### Packaged apps — remaining reports (M4.1-4)

- [ ] Revise experience reports (already drafted for 0.5)
- [ ] Application gallery page on hop3.cloud
- [ ] Per-app README with deployment instructions

### Paper follow-up (M5.3)

- [ ] Address reviewer feedback (if submitted in 0.5)
- [ ] Final camera-ready version
- [ ] Archive on HAL/arXiv

### Source builds (continued from 0.5)

- [ ] Complete remaining Go source builds started in 0.5
- [ ] Grafana, Mattermost, Focalboard: source build or documented deferral
- [ ] Update reproducibility assessment in ADR 008

### Multi-component apps (continued from 0.5)

- [ ] Implement `[run.workers]` for NextCloud cron, Invoice Ninja queue
- [ ] Test Mastodon-like multi-service deployment if ADR is accepted

### Release mechanics

- [ ] Update version to 0.6.0
- [ ] Write CHANGELOG
- [ ] Tag v0.6.0
- [ ] Blog post: "Hop3 0.6: NGI Complete"
- [ ] Final NGI project report

## Out of Scope for 0.6

These are valuable but not NGI commitments:

- Agent model (ADR 017) — post-NGI, towards 0.7/1.0
- SSO / identity management — post-NGI
- Monitoring / metrics dashboard — post-NGI
- Multi-server / distributed deployment — post-NGI (JumpGATE)
- Marketplace — post-NGI

## Effort Estimate

| Area | Days |
|------|------|
| Firewall/WAF integration (M3.5) | 5-7 |
| Upgrade mechanism (M3.2) | 3 |
| Backup migration (M3.3) | 2 |
| Paper benchmarks (M5.3) | 4-5 |
| Paper final + submit (M5.3) | 2 |
| Screencasts (M5.6) | 2-3 |
| Web UI polish (M3.7) | 4 |
| Security external review (M3.8) | 2 |
| Email addon (if not in 0.5) | 2-3 |
| Experience reports finalization (M4) | 3 |
| Release mechanics | 1 |
| **Total** | **~30-35 days** |

## Risk Register

| Risk | Mitigation |
|------|------------|
| External security review delays | Submit early; proceed with internal assessment if external review is slow |
| Paper rejected | Re-submit to workshop venue; archive on HAL regardless |
| 21 days doesn't fit in 4 weeks | Prioritise NGI-visible deliverables (M4 reports, M5.3); defer UI polish if needed |
