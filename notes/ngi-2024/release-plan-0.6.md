# Hop3 0.6.0 Release Plan

**Target:** June 2026
**Theme:** Completion and dissemination — finish the operational subsystems and put the documentation and design record into a published, audited form
**Depends on:** 0.5.0 released (tagged 2026-04-22)
**Last updated:** 2026-06-20 — reframed as an intermediate release; the final NGI deliverable is now 0.7 (see `release-plan-0.7.md`).

## Goals

0.6 is **not** the final NGI deliverable release; that role moves to 0.7 (`release-plan-0.7.md`). 0.6 is the cycle that closes the operability work begun in 0.5 and turns the documentation and the design record into a form a reviewer can read end to end. Its dominant theme is dissemination: the ADR corpus, the testing-architecture narrative, the migration series, and the second interim technical report. A small number of subsystem milestones also completed in this window; the rest are carried forward to 0.7 with their state recorded plainly.

This file records **what was actually done** in the 0.6 cycle (~190 commits since the 0.5.0 tag). Items still open at the close of 0.6 are listed under "Carried to 0.7" and planned in `release-plan-0.7.md`.

## NGI Milestone Status After 0.6

| Milestone | 0.5 Status | 0.6 Outcome |
|-----------|-----------|-------------|
| M2.2 Nix runtime beta | Stabilised | Catalogue maintained; several deferred apps recovered |
| M2.3 Nix runtime 1.0 | Not started | → 0.7 (docs polish, CI, release notes) |
| M3.1 Backing services | + S3 addon | S3 shipped in 0.5; email addon → 0.7 |
| M3.2 Upgrades | Partial | Upgrade path hardened (migrations on upgrade, venv preserved); production `hop3 upgrade` → 0.7 |
| M3.3 Backup migration | Not tested | **Done** — automated cross-server test |
| M3.5 Firewalls/WAF | Network design | Network firewall/port registry hardened (Final); WAF → 0.7 |
| M3.6 CLI | Working | Refinements landed; ADR 042 Accepted, ADR 047 drafted |
| M3.7 Web UI | Reviewed | Carried; Git-URL deploy stub present but disabled → 0.7 |
| M3.8 Security audit | 4 code fixes done | Code fixes shipped; external review → 0.7 |
| M4.1-4 Packaged apps | Reports drafted | 159 app configs; standalone reports remain Draft; production traffic → 0.7 |
| M5.1 Website / blog | Shipped | **Extended** — 22 posts incl. testing series, 0.5.0 release, migration series started |
| M5.2 Documentation | Shipped | **Audited** — accuracy pass against the code; full ADR corpus published |
| M5.3 Paper — benchmarks | Not started | → 0.7 |
| M5.3 Paper — interim | TR-01 refreshed | **Done** — TR-02 written |
| M5.6 Screencasts | Not started | → 0.7 |

## What shipped in 0.6

### Dissemination and documentation (T5) — DONE

- [x] **ADR corpus published.** `docs/scripts/convert_adrs.py` publishes all 49 ADRs from `notes/adrs/` to `docs/src/developers/adrs/`, rewriting cross-links and generating a status-grouped index in the navigation. The design record is now part of the documentation site rather than living only in the source tree.
- [x] **ADR accuracy and voice pass.** All ADRs reviewed against the conventions in `000-readme.md`: status vocabulary normalised, stale "draft/deferred" statuses corrected to reflect shipped work, and the prose brought to a timeless architectural-record voice (no changelog-style play-by-play, no line/test counts).
- [x] **Documentation accuracy audit against the code.** A full pass corrected drift between the docs and the shipped behaviour: the old colon command syntax replaced by the space form (ADR 036), the test taxonomy updated to the three-layer model (`a_unit`/`b_integration`/`c_e2e`, ADR 043), the build tool corrected from MkDocs to Zensical, a documented-but-unimplemented `logs --follow` flag removed, and all tutorials fixed.
- [x] **Blog.** The 0.5.0 release post; a five-part series on the testing architecture (overview, runner, Test Lab, demos, executable-docs/validoc); and the first "migrating from X" post (Heroku). Conference posts for OW2Con 2025 and OSXP 2025 are live.
- [x] **Diagrams.** ASCII-art diagrams across the docs aligned and, where the renderer supports it, converted to Mermaid.
- [x] **TR-02.** The second interim technical report, covering the 0.5 and 0.6 cycles and complementing TR-01 without restating it.

### Resilience (T3, M3.3) — DONE

- [x] **Automated cross-server backup-migration test** (`packages/hop3-server/tests/c_e2e/test_backup_migration.py`): backup on instance A, transfer, register, and restore on instance B, with negative-path coverage (corrupted backup refused, name-collision handling, manifest round-trip, byte-equal source tree).
- [x] **Backups capture all app data** — volume data and the app `data/` directory are now archived.

### CLI (T3, M3.6) — refinements landed

- [x] Post-ADR-036 renames and cleanups: `launch`→`create`, `backup info`→`backup show`, `addon ps`→`addon activity`, `env`→`app migrate`, `domains`→`domain`.
- [x] Dropped the deprecated positional-app fallback — the app target is `--app` only (ADR 036 D5).
- [x] **ADR 042 (CLI context model)** Accepted: the server/context vocabulary split. **ADR 047 (CLI invocation context)** drafted.

### Upgrade path hardening (T3, M3.2) — groundwork

- [x] Deploy/upgrade now runs database migrations and no longer clobbers the application venv on upgrade.
- [x] `db:upgrade` adopts unstamped pre-Alembic databases; freshly created databases are stamped at head on bootstrap.
- Production `hop3 upgrade` command and app-level upgrade orchestration → 0.7.

### Network firewall (T3, M3.5) — hardened

- [x] Fixed-port registry teardown hardened; firewall errors now fail loud rather than passing silently. **ADR 045 (Fixed-Port Registry)** is Final and supersedes ADR 040.
- WAF (Coraza / OWASP-CRS) → 0.7.

### Application catalogue (T4) — maintained

- [x] 159 app configurations: 41 native, 34 hand-crafted Nix, 31 template-generated Nix, 53 Docker.
- [x] Several previously deferred Nix apps recovered into working variants (etherpad → nix-gen, listmonk → nix-gen, matrix-synapse → nix). HedgeDoc and CryptPad remain under `apps/bad/` with `DEFERRED.md` notes pointing at the platform gap.

## Carried to 0.7 (the final NGI deliverable)

Planned in `release-plan-0.7.md`:

- M2.3 — Nix runtime "1.0" (docs polish, CI integration, release notes).
- M3.1 — email/SMTP addon.
- M3.2 — production `hop3 upgrade` command, app-level upgrade orchestration, rollback on failure.
- M3.5 — WAF (Coraza / OWASP-CRS) integration.
- M3.7 — web UI: Git-URL deploy (the form field exists but is disabled), real-time log streaming, visual/accessibility review, mobile-responsive check.
- M3.8 — external security review and accessibility scan.
- M4 — production-traffic deployments and finalisation of the 20 experience reports (currently Draft).
- M5.3 — quantitative benchmarks and final paper submission.
- M5.6 — two screencasts ("Zero to Running App", "Dashboard Tour").
- T5 — publish the remaining 21 "migrating from X" drafts.

## Release mechanics (0.6)

- [ ] Add the missing `[0.5.0]` changelog entry, then a `[0.6.0]` entry (the changelog currently skips from `[0.4.0]` to `[Unreleased]`).
- [ ] Bump version to 0.6.0 across `pyproject.toml` (still 0.5.0).
- [ ] Tag v0.6.0.
- [ ] Blog post: "Hop3 0.6: Documentation, Testing, and the Migration Series".

## Out of Scope for 0.6

Valuable but not NGI commitments, post-NGI (towards 0.7+/1.0): the agent model (ADR 017), SSO / identity management, a monitoring / metrics dashboard, multi-server / distributed deployment (JumpGATE), and a marketplace.
