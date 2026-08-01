# Hop3 0.6.0 Release Plan

**Target:** June 2026
**Theme:** Resource controls and a richer addon surface, the app catalog, and the documentation and design record put into a published, audited form
**Depends on:** 0.5.0 released (tagged 2026-06-08)
**Last updated:** 2026-06-20. Reframed as an intermediate release; the final NGI deliverable is now 0.7 (see `release-plan-0.7.md`).

## Goals

0.6 is **not** the final NGI deliverable release; that role moves to 0.7 (`release-plan-0.7.md`). 0.6 ships real platform capability on top of the operability work of 0.5: per-app resource limits and volumes (ADR 046 Phase 2), a much richer addon-management surface, and the signed app-catalog distribution mechanism (ADR 049). In parallel it turns the documentation and the design record into a form a reviewer can read end to end (the published ADR corpus, the testing and migration series, and the second interim technical report). The milestones still open at the close of 0.6 are carried forward to 0.7 with their state recorded plainly.

This file records **what was actually done** in the 0.6 cycle (~190 commits since the 0.5.0 tag). Items still open at the close of 0.6 are listed under "Carried to 0.7" and planned in `release-plan-0.7.md`.

## NGI Milestone Status After 0.6

| Milestone | 0.5 Status | 0.6 Outcome |
|-----------|-----------|-------------|
| M2.2 Nix runtime beta | Stabilised | Catalogue maintained; several deferred apps recovered |
| M2.3 Nix runtime 1.0 | Not started | → 0.7 (docs polish, CI, release notes) |
| M3.1 Backing services | + S3 addon | **Addon-management surface greatly expanded** (query/diagnostics/clone/export-import/expose/promote/tunnel); email addon → 0.7 |
| M3.2 Upgrades | Partial | Upgrade path hardened (migrations on upgrade, venv preserved); production `hop3 upgrade` → 0.7 |
| M3.3 Backup migration | Not tested | **Done**: automated cross-server test |
| M3.5 Firewalls/WAF | Network design | Network firewall/port registry hardened (Final); WAF → 0.7 |
| M3.6 CLI | Working | Refinements landed; ADR 047 drafted (on the ADR-042 model from 0.5) |
| M3.7 Web UI | Reviewed | Carried; Git-URL deploy stub present but disabled → 0.7 |
| M3.8 Security audit | 4 code fixes done | Code fixes shipped; external review → 0.7 |
| M4.1-4 Packaged apps | Reports drafted | 159 app configs; standalone reports remain Draft; production traffic → 0.7 |
| M5.1 Website / blog | Shipped | **Extended**: 23 posts incl. testing series, 0.5.0 release, migration series started, OW2Con 2026 |
| M5.2 Documentation | Shipped | **Audited**: accuracy pass against the code; full ADR corpus published |
| M5.3 Paper: benchmarks | Not started | → 0.7 |
| M5.3 Paper: interim | TR-01 refreshed | **Done**: TR-02 written |
| M5.6 Screencasts | Not started | → 0.7 |

Beyond the named milestones, 0.6 also delivered two cross-cutting platform features (**resource limits and volumes**, ADR 046 Phase 2, and the **signed app-catalog distribution**, ADR 049 and ADR 031), plus a secret/config single-sourcing fix (ADR 048).

## What shipped in 0.6

### Resource limits and volumes (ADR 046 Phase 2): DONE

- [x] **`[limits]` resource caps.** Declare per-app memory and CPU limits in `hop3.toml`, resolved against a server-wide default and ceiling policy. Enforced for native apps via cgroup v2 (through `rootd`) and for Docker apps via the deployer.
- [x] **Out-of-memory visibility.** `hop3 app status` reports the active caps and any OOM kills; the App model carries `limits_enforced` / `limits_detail`.
- [x] **Volumes.** Apps can mount persistent bind volumes and tmpfs, applied by `rootd` behind a default-deny allow-list and reconciled (mounts and cgroup leaves) at startup.

### Addon-management surface (T3, M3.1): DONE

- [x] **Consistent `addon <type> <verb>` commands** across PostgreSQL/MySQL/Redis/S3: ad-hoc `query` (SQL / `redis-cli`, least-privilege), read-only diagnostics (`ps`, `locks`, `settings`, redis `info`), `clone`, and `export`/`import` streaming a dump via stdin/stdout, with confirmation on the destructive verbs (`restore`/`flush`).
- [x] **Lifecycle and access:** `addon exists` (predicate), `addon promote` with per-addon variable namespacing, `addon endpoint`, `addon expose`/`unexpose` (server-side TCP forwarders via a `rootd` `proxy.*` op), and `hop3 tunnel` to reach an addon from a developer machine.

### App-catalog distribution (ADR 049, ADR 031): DONE

- [x] **Signed central catalog.** Hop3 verifies and loads an installable-app catalog from a signed central source; `hop3 catalog refresh` and setup-time sync keep it current (canonical URL `https://apps.hop3.cloud/catalog/`).
- [x] **Publisher tooling:** `hop3-catalog validate` (gate content specs) and `hop3-catalog publish` (build + sign the catalog tarball).
- [x] **Dashboard hardened** (README sanitised, raster-only icons, unavailable banner) and the taxonomy extended (Business/Content/Identity/News/Monitoring categories). The former "marketplace" is renamed "catalog" per ADR 031.

### Dissemination and documentation (T5): DONE

- [x] **ADR corpus published.** `docs/scripts/convert_adrs.py` publishes all ADRs from `notes/adrs/` to `docs/src/developers/adrs/`, rewriting cross-links and generating a status-grouped index in the navigation. The design record is now part of the documentation site rather than living only in the source tree.
- [x] **ADR accuracy and voice pass.** All ADRs reviewed against the conventions in `000-readme.md`: status vocabulary normalised, stale "draft/deferred" statuses corrected to reflect shipped work, and the prose brought to a timeless architectural-record voice (no changelog-style play-by-play, no line/test counts).
- [x] **Documentation accuracy audit against the code.** A full pass corrected drift between the docs and the shipped behaviour: the old colon command syntax replaced by the space form (ADR 036), the test taxonomy updated to the three-layer model (`a_unit`/`b_integration`/`c_e2e`, ADR 043), the build tool corrected from MkDocs to Zensical, a documented-but-unimplemented `logs --follow` flag removed, and all tutorials fixed.
- [x] **Blog.** The 0.5.0 release post; a five-part series on the testing architecture (overview, runner, Test Lab, demos, executable-docs/validoc); and the first "migrating from X" post (Heroku). Conference posts for OW2Con 2025, OSXP 2025, and OW2Con 2026 are live.
- [x] **Diagrams.** ASCII-art diagrams across the docs aligned and, where the renderer supports it, converted to Mermaid.
- [x] **TR-02.** The second interim technical report, covering the 0.5 and 0.6 cycles and complementing TR-01 without restating it.

### Resilience (T3, M3.3): DONE

- [x] **Automated cross-server backup-migration test** (`packages/hop3-server/tests/c_e2e/test_backup_migration.py`): backup on instance A, transfer, register, and restore on instance B, with negative-path coverage (corrupted backup refused, name-collision handling, manifest round-trip, byte-equal source tree).
- [x] **Backups capture all app data**: volume data and the app `data/` directory are now archived.

### CLI (T3, M3.6): refinements landed

- [x] Post-ADR-036 renames and cleanups: `launch`→`create`, `backup info`→`backup show`, `addon ps`→`addon activity`, the Procfile importer `env migrate`→`app migrate`, `domains`→`domain`, and account creation consolidated under `user add`. Old spellings kept as aliases.
- [x] Dropped the deprecated positional-app fallback: the app target is `--app` only (ADR 036 D5).
- [x] **ADR 047 (CLI invocation context)** drafted, building on the ADR-042 server/context model that shipped in 0.5.

### Upgrade path hardening (T3, M3.2): groundwork

- [x] Deploy/upgrade now runs database migrations and no longer clobbers the application venv on upgrade.
- [x] `db:upgrade` adopts unstamped pre-Alembic databases; freshly created databases are stamped at head on bootstrap.
- Production `hop3 upgrade` command and app-level upgrade orchestration → 0.7.

### Network firewall (T3, M3.5): hardened

- [x] Fixed-port registry teardown hardened; firewall errors now fail loud rather than passing silently. **ADR 045 (Fixed-Port Registry)** is Final and supersedes ADR 040.
- WAF (LeWAF / OWASP CRS) → 0.7.

### Secret single-sourcing and deploy reliability (T3): DONE

- [x] **`HOP3_SECRET_KEY` single-sourced** in `/etc/hop3/secret-key` (ADR 048), ending the environment-vs-config desync that could leave addon credentials unreadable after a restart. Redeploys are idempotent: they reuse existing DB secrets and preserve operator config rather than regenerating them.
- [x] **Redeploy no longer SIGTERMs its own in-flight `git receive-pack`** (the process reaper now spares its own tree); stable app port across redeploys; static sites without a Procfile served via `[build].static-dir`; build-output dirs (`target/`) excluded from the upload; Redis health check authenticates when `REDIS_PASSWORD` is unset.

### Packaged-application catalogue (T4): maintained

(The set of packaged app *configs*, distinct from the catalog-distribution mechanism above.)

- [x] 159 app configurations: 41 native, 34 hand-crafted Nix, 31 template-generated Nix, 53 Docker.
- [x] Several previously deferred Nix apps recovered into working variants (etherpad → nix-gen, listmonk → nix-gen, matrix-synapse → nix). HedgeDoc and CryptPad remain under `apps/bad/` with `DEFERRED.md` notes pointing at the platform gap.

## Carried to 0.7 (the final NGI deliverable)

Planned in `release-plan-0.7.md`:

- M2.3: Nix runtime "1.0" (docs polish, CI integration, release notes).
- M3.1: email/SMTP addon.
- M3.2: production `hop3 upgrade` command, app-level upgrade orchestration, rollback on failure.
- M3.5: WAF (LeWAF / OWASP CRS) integration.
- M3.7: web UI: Git-URL deploy (the form field exists but is disabled), real-time log streaming, visual/accessibility review, mobile-responsive check.
- M3.8: external security review and accessibility scan.
- M4: production-traffic deployments and finalisation of the 20 experience reports (currently Draft).
- M5.3: quantitative benchmarks and final paper submission.
- M5.6: two screencasts ("Zero to Running App", "Dashboard Tour").
- T5: publish the remaining 21 "migrating from X" drafts.

## Release mechanics (0.6)

- [x] `CHANGES.md`: `[0.5.0]` entry slimmed to a "what"-level summary, and a `[0.6.0]` entry added (with footer compare links).
- [ ] Bump version to 0.6.0 across `pyproject.toml` (still 0.5.0).
- [ ] Tag v0.6.0.
- [ ] Blog post: "Hop3 0.6: Documentation, Testing, and the Migration Series".

## Out of Scope for 0.6

Valuable but not NGI commitments, post-NGI (towards 0.7+/1.0): the agent model (ADR 017), SSO / identity management, a monitoring / metrics dashboard, and multi-server / distributed deployment (JumpGATE).
