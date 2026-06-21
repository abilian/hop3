# Hop3 0.7.0 Release Plan — Final NGI Version

**Target:** Late 2026
**Theme:** Complete all remaining NGI commitments
**Depends on:** 0.6.0 released
**Last updated:** 2026-06-20 — created when 0.7 became the final NGI deliverable release (see `release-plan-0.6.md` for the 0.6 outcome).

## Goals

0.7 is the final NGI deliverable release. Every milestone from the project plan (#2024-04-365) must be either complete or carry a documented, justified deferral agreed with the NGI reviewers. The 0.5 cycle made the platform operable; the 0.6 cycle published the documentation and the design record. 0.7 closes the remaining subsystem milestones and delivers the quantitative evaluation that gates the final report.

The remaining work, and the only blocking chain, is the quantitative evaluation:

```
Benchmark harness ──▶ Measurements ──▶ Final report / paper (M5.3)
   (4-5 days)            (2 days)           (2 days)
```

Everything else can run in parallel with it.

## NGI Milestone Completion Matrix

Carried from 0.6 (`release-plan-0.6.md`):

| Milestone | State entering 0.7 | 0.7 Target |
|-----------|--------------------|------------|
| M2.3 Nix runtime 1.0 | Beta running; no 1.0 cut | Docs polish, CI, release notes |
| M3.1 Email addon | Not started | SMTP-relay addon |
| M3.2 Upgrades | Upgrade path hardened | Production `hop3 upgrade`, rollback |
| M3.5 Firewalls/WAF | Network firewall Final | WAF (LeWAF / OWASP CRS) |
| M3.7 Web UI | Stub Git-URL field | Git-URL deploy, log streaming, a11y review |
| M3.8 Security audit | 4 code fixes shipped | External review + accessibility scan |
| M4.1-4 Packaged apps | 159 configs; Draft reports | Production traffic, finalised reports |
| M5.3 Paper — benchmarks | Not started | Done |
| M5.3 Paper — final | TR-02 written | Submitted and published |
| M5.6 Screencasts | Not started | 2 screencasts published |

## Scope

### Paper benchmarks (M5.3) — the gating item

Plan at `local-notes/plans/05-paper-benchmarks.md`.

- [ ] Set up comparison baseline (Dokku + K3s, or Docker Compose + bare uWSGI)
- [ ] Benchmark 1: control-plane memory footprint (0, 10, 28 apps)
- [ ] Benchmark 2: deployment latency by build strategy (native vs Nix template vs Docker)
- [ ] Benchmark 3: Nix closure size vs Docker image size for the Tier-1 corpus
- [ ] Benchmark 4: cold-start latency
- [ ] Benchmark 5: bit-for-bit reproducibility across independent rebuilds of the Tier-1 corpus
- [ ] Integrate results into the paper's evaluation section
- [ ] Submit the paper; archive on HAL regardless of venue outcome

### Nix runtime 1.0 (M2.3)

- [ ] Documentation polish: finalise the `hop3.nix` / `[nix]` reference and the source-builds vs pre-built-binaries reproducibility tiers
- [ ] CI integration: `make test-nix` wired into the nightly Test Lab, persisting `/nix/store` between runs
- [ ] Recover or formally defer the remaining bad apps (HedgeDoc, CryptPad)
- [ ] Release notes for the Nix runtime

### Upgrade mechanism (M3.2)

The upgrade path was hardened in 0.6 (migrations run on upgrade; the venv is preserved; pre-Alembic databases are adopted). 0.7 adds the production command surface.

- [ ] `hop3 server upgrade` (pull latest, run migrations, restart services)
- [ ] `hop3 app upgrade --app <app>` (re-deploy from latest source)
- [ ] Rollback on failure (keep the previous version)
- [ ] Document the upgrade procedure in the admin guide

### Email addon (M3.1)

- [ ] SMTP-relay design (point at the operator's existing provider; running a mail server is out of scope for a PaaS)
- [ ] `addon create email <name> --smtp-host <h> --smtp-user <u>` stores encrypted SMTP credentials
- [ ] Inject `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM` into attached apps
- [ ] Document in `docs/src/guides/addons.md`

### Firewall / WAF integration (M3.5)

The network-level firewall and fixed-port registry shipped (ADR 045, Final). 0.7 adds the application-layer WAF. Research notes in `local-notes/lewaf/`.

- [ ] Review the LeWAF / OWASP CRS approach and write the WAF ADR (deferred from ADR 040)
- [ ] WAF plugin architecture: per-app enable/disable in `hop3.toml` (likely under `[security]`)
- [ ] nginx integration module with the OWASP Core Rule Set
- [ ] Test against the OWASP Top 10 (SQLi, XSS, path traversal at minimum)
- [ ] False-positive management and per-app exemptions
- [ ] Document in the admin guide

### Web UI polish (M3.7)

The dashboard exists (9 controllers, 17 templates). The Git-URL deploy form field is present but disabled ("Coming Soon").

- [ ] Wire the Git-URL deploy path end to end (the controller already parses `git_url`; it is currently ignored)
- [ ] Real-time log streaming in the browser
- [ ] Visual review with a UX-aware reviewer
- [ ] Accessibility (a11y) scan and fixes for critical issues
- [ ] Mobile-responsive layout check

### Security external review (M3.8)

The four internal-audit code fixes shipped in 0.5 (magic-link default removed, auth rate-limiting, RFC-7235 bearer matching, configurable token lifetime).

- [ ] Engage the external NGI security review; address feedback
- [ ] Accessibility scan (covered jointly with M3.7)
- [ ] Document the security model in the admin guide

### Screencasts (M5.6)

The 34 scripted demos under `demos/` are the basis (walkthrough + screencast source + regression test).

- [ ] Finalise the two scripts (~1 page each)
- [ ] Clean dev VM, fresh Hop3 install, dry-run the demos
- [ ] Record "Zero to Running App in 5 Minutes" (asciinema for terminal, OBS for browser)
- [ ] Record "Dashboard Tour" (browser screen recording)
- [ ] Edit, caption, export, upload to the website + PeerTube
- [ ] Embed the videos in the getting-started docs

### Packaged apps — production traffic and reports (M4.1-4)

20 standalone experience reports exist under `notes/experience-reports/` (Draft, 0.5). This finalises them against real deployments.

- [ ] Deploy at least 5 apps to production with real traffic for 1+ week (Miniflux, Gitea, WordPress, Etherpad, NextCloud)
- [ ] Finalise the experience reports from production experience
- [ ] Application gallery page on hop3.cloud

### Migration series (T5)

- [ ] Publish the 21 drafted "migrating from X" posts (`local-notes/blog/`) on a staggered schedule

### Release mechanics

- [ ] Ensure `[0.5.0]` and `[0.6.0]` changelog entries exist, then add `[0.7.0]`
- [ ] Bump version to 0.7.0
- [ ] Tag v0.7.0
- [ ] Blog post: "Hop3 0.7: NGI Complete"
- [ ] Final NGI project report

## Out of Scope for 0.7

Valuable but not NGI commitments, deferred post-NGI: the agent model (ADR 017), SSO / identity management, a monitoring / metrics dashboard, multi-server / distributed deployment (JumpGATE), and a marketplace.

## Effort Estimate

| Area | Days |
|------|------|
| Paper benchmarks + measurements (M5.3) | 6-7 |
| Paper final + submit (M5.3) | 2 |
| Nix runtime 1.0 (M2.3) | 3 |
| Upgrade command (M3.2) | 3 |
| Email addon (M3.1) | 2-3 |
| Firewall/WAF integration (M3.5) | 5-7 |
| Web UI polish (M3.7) | 4 |
| Security external review (M3.8) | 2 |
| Screencasts (M5.6) | 2-3 |
| Production deploys + experience reports (M4) | 4 |
| Migration-series publishing (T5) | 1 |
| Release mechanics | 1 |
| **Total** | **~35-40 days** |

## Risk Register

| Risk | Mitigation |
|------|------------|
| Benchmarks reveal Hop3 is slower than a baseline | Report accurately; the paper's contribution is the architecture and reproducibility story, not raw speed |
| External security review delays | Submit findings early; proceed with the internal assessment if the external review is slow |
| WAF false-positive tuning overruns | Ship a conservative default rule set; document per-app exemptions; treat aggressive tuning as post-NGI |
| Production deploys uncover blocker bugs | Triage: fix critical, defer the rest with notes |
| Time runs short before all milestones close | Prioritise the gating item (M5.3) and NGI-visible deliverables; cut UI polish first |

## Definition of Done (whole release)

- [ ] Quantitative benchmarks run and integrated into the paper (M5.3)
- [ ] Paper submitted and archived (M5.3)
- [ ] Production `hop3 upgrade` with rollback (M3.2)
- [ ] Email addon shipped (M3.1)
- [ ] WAF integrated with the OWASP Core Rule Set (M3.5)
- [ ] Web UI Git-URL deploy and log streaming (M3.7)
- [ ] External security review addressed; accessibility scan done (M3.8)
- [ ] Two screencasts published (M5.6)
- [ ] At least 5 production deployments with finalised experience reports (M4)
- [ ] Migration series published (T5)
- [ ] v0.7.0 tagged and announced; final NGI report submitted
