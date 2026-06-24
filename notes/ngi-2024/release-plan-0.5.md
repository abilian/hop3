# Hop3 0.5.0 Release Plan

**Released:** 2026-06-08 (see CHANGES.md `[0.5.0]`)
**Theme:** Consolidation — make what we have solid and demonstrable
**Branch:** `main` (merged from `nix-builders`)
**Last updated:** 2026-06-08

## Goals

Version 0.5 closed the gaps that prevented demonstrating Hop3 to the NGI reviewers. It did not add major new features — it made existing features reliable, documented, and presentable. This plan is retained as a shipped-release retrospective; see CHANGES.md `[0.5.0]` for the final set of changes.

## Critical path

```
Paper benchmarks ──▶ Tech report review ──▶ Paper submission (M5.3)
   (4-5 days)            (1 day)
```

This is the longest blocking chain. Everything else can run in parallel.

## Scope

### Nix runtime stabilisation and completion (M2.2 + M2.3)

#### Triage `apps/bad/real-apps-nix-bad/` (8 apps) — TRIAGED

All 8 apps debugged on Docker target (2026-04-11). Root causes identified for all; full report at `/tmp/nix-triage/findings.md`.

**Infrastructure bugs found and fixed (c65f5509):**
- Bundler silent name collision (`_has_systemd` in nix.py vs s3.py)
- `has_systemd()` false-positive in containers → shared `/proc/1/comm`-based helper in `common.py`
- Single-user nix never wrote `sandbox = relaxed` → `__noChroot` rejected
- Bundler now AST-detects top-level name collisions
- Test log writer missing `mkdir parents=True`

**Infrastructure bugs flagged, remaining:**
- `postgres.py` supervisord fallback — **SHIPPED (W16)** via `pg_ctlcluster` (Debian) / `pg_ctl` (Fedora)
- hop3-server wraps `RepositoryError` as opaque "data processing" error on redeploys — open
- Test runner deploy-timeout doesn't kill orphaned nix-build — open

**Per-app triage:**

Trivial fixes (~1 hour total) — **DONE (W16)**:
- [x] **searxng** — replaced hand-crafted `hop3.nix` with `nixpkgs-wrapper`
- [x] **xwiki** — heredoc quoting fixed via sed-substitution with `__APPDIR__`/`__JDK__` placeholders + symlink into writable cwd
- [x] **matrix-synapse** — placeholders renamed to `__VENV__`/`__ZSTDLIB__`; added `pillow.libs/` to `LD_LIBRARY_PATH`; auto-generates `homeserver.yaml`

Medium fixes (1-3 hours each):
- [ ] **hedgedoc** — `Cannot find module 'express'` (node_modules
      from release tarball lost during cp to Nix store)
- [ ] **matrix-synapse** — also needs libzstd LD_LIBRARY_PATH fix
- [ ] **etherpad** — build OK; runtime masked by hop3-server
      RepositoryError on retry deploys; needs clean re-run
- [ ] **cryptpad** — `npm install` exceeds 10-min deploy timeout;
      try `pkgs.cryptpad` or raise nix-slow tier timeout

Re-evaluate / drop:
- [ ] **listmonk** — SMTP-relay reasoning was wrong (listmonk
      stores SMTP creds in its own DB). Viable via `pkgs.listmonk`
      from nixpkgs; or drop if not in nixpkgs.
- [x] **sonarqube** — dropped. Bundled ES 8.19 crashes on startup
      (`vm.max_map_count` + heap). Deferred to `apps/bad/` with
      `DEFERRED.md`. Also: read-only Nix store + amd64-only +
      source-available licensing make it a poor fit.

#### Static site Nix worker — DONE

- [x] `static-hello` test app passes via SSH (root cause fix in
      `get_static_paths()` shipped W15)
- [x] `static-hello` test app passes on Docker target (verified)
- [x] Added regression test app: `apps/real-apps-nix/landing/`
      (multi-page HTML + CSS, validates index, second page, and CSS
      asset). Both `static-hello` and `landing` PASS on Docker.
- [x] Bumped `body_preview` 500 → 4096 chars in test framework so
      `contains` checks see beyond the head/header (was masking the
      regression test until fixed).

#### Documentation — DONE

- [x] Rewrote `docs/src/guides/nix-deployment.md`: now leads with
      template mode + `nixpkgs-wrapper`, has explicit
      "Source builds vs pre-built binaries" section, and
      reproducibility tier table. Hand-crafted hop3.nix moved to
      "escape hatch" status. (323 → 393 lines.)
- [x] Updated `docs/src/reference/nix.md`: removed "Phase 1" claim
      (which said no auto-generation), documented both modes (template
      + hand-crafted), runtime.json contract, all 8 templates with
      tiers, build process flow. (233 → 265 lines.)
- [x] Added "Source builds vs pre-built binaries" content to the
      guide (promoted from `notes/experience-reports/00-aggregate.md`
      and `notes/ngi-2024/plan-source-builds.md`).
- [x] Documented `hop3 nix eject` in CLI reference (`cli.md`) under
      a new "Nix Commands" section, with usage, behavior, errors, and
      cross-references.
- [x] Updated `[nix]` section in `config.md`: now lists all 8 templates
      (was 7 — added `ruby-bundler`), with reproducibility tiers per
      template. Switched the canonical Gitea example from
      `prebuilt-binary` to `nixpkgs-wrapper` to model the recommended
      approach.

#### CI

- [ ] Add `make test-nix` target running `hop3-test system --docker --with nix apps/test-apps-nix apps/real-apps-nix-gen`
- [ ] Wire into SourceHut CI on every push to `main` and `devel`
- [ ] Caching: persist `/nix/store` between runs to avoid re-downloads

### Source builds for Go apps (replace pre-built binaries) — DONE

6 of 7 Nix apps converted from pre-built binaries to nixpkgs source builds via the `nixpkgs-wrapper` template. Multi-arch support gained (aarch64, ARM, RISC-V, etc.). See `plan-source-builds.md`.

- [x] Miniflux: `pkgs.miniflux` (built from source by nixpkgs)
- [x] Gitea: `pkgs.gitea`
- [x] Grafana: `pkgs.grafana` (+ switched from SQLite to PostgreSQL)
- [x] Mattermost: `pkgs.mattermost`
- [x] Vikunja: `pkgs.vikunja` (added publicurl for v2.2.2 compat)
- [x] Wiki.js: hand-crafted variant uses nixpkgs source + node;
      nix-gen variant stays on `node-prebuilt` (nixpkgs ships wiki-js
      as raw source tree, no `bin/wiki-js` wrapper)
- [ ] Focalboard: not in nixpkgs (upstream archived 2023). **Decision
      needed:** drop, replace with maintained alternative, or keep
      with explicit deprecation notice. Recommendation: drop (Vikunja
      already covers task management).

### Multi-component app support (ADR 038) — DESIGN DONE

- [x] Written: `notes/adrs/038-multi-service-apps.md`
- [x] Distinguishes `[run.workers]` (shared-env flat workers) from
      new `[[component]]` table (per-component env, memory limits,
      health checks, scaling)
- [x] Survey of Heroku/Render/Fly.io/K8s models
- [x] Mastodon example showing the target shape
- [x] Phased implementation plan (parser → runtime → advanced)
- [ ] Implementation deferred to 0.6 (Phases 1+2)

### Security fixes (M3.8 completion) — CODE DONE

- [x] Remove magic link default username (no more `default="admin"` in CLI)
- [x] Add rate limiting to auth endpoints (in-memory sliding window,
      5 req/min/IP on `/auth/login` and `/auth/magic/{token}`)
- [x] Fix bearer token case sensitivity (RFC 7235 — auth-scheme is
      case-insensitive)
- [x] Make session lifetime configurable (`HOP3_TOKEN_EXPIRY_HOURS`
      now read by `create_token()`)
- [ ] Contact NGI security audit team for external review

### Backing services (M3.1) — S3 DONE

The current addon set (PostgreSQL, MySQL, Redis) covered most applications but left visible gaps for apps that need object storage or email. The 0.5 goal was to add at least one; S3 shipped.

#### S3-compatible storage addon — DONE

- [x] Created `hop3/plugins/s3/` with a backend abstraction so the
      MinIO variant can be swapped for Garage in a future release
- [x] MinIO backend: `addons:create s3 <name>` provisions a bucket
      and a per-addon access key via `mc admin user add` + IAM policy
- [x] Installer integration: `hop3-install server --with s3` downloads
      MinIO + `mc`, writes credentials, installs systemd unit (with
      supervisord fallback for containers), and exposes
      `MC_HOST_hop3` to the hop3 user via `/etc/hop3/s3-env`
- [x] `addons:attach <addon> <app>` injects
      `S3_ENDPOINT`/`S3_BUCKET`/`S3_ACCESS_KEY`/`S3_SECRET_KEY`/`S3_REGION`
- [x] CLI parity: `addons:info`, `addons:list`, `addons:destroy`
- [x] Integration test: `apps/test-apps-procfile/flask-s3` reads/writes
      to the addon end-to-end (passes on SSH + Docker targets)

**Licensing note:** MinIO moved toward source-available in 2025. The
plan is to replace it with Garage (truly AGPL) in a future release — the backend abstraction already exists to make the swap a one-liner on the plugin side.

#### Email addon (stretch — did NOT ship in 0.5 or 0.6; reslotted to 0.7)

The email/SMTP addon is not in the 0.6 changelog; it is now a 0.7 deliverable.

- [ ] Design decision: SMTP relay config vs full mail server?
      Recommendation: SMTP relay only (point at user's existing
      provider) — running a mail server is out of scope for a PaaS.
- [ ] `addon email create <name> --smtp-host <h> --smtp-user <u>`
      stores encrypted SMTP credentials
- [ ] Injects `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`,
      `SMTP_FROM` into attached apps
- [ ] Document in `docs/src/guides/addons.md`

#### Documentation

- [ ] Document all addons in `docs/src/guides/addons.md` — supported,
      new, and planned
- [ ] Add `[env]` mapping examples for each addon type (how to map
      `PGHOST`/`PGPORT` to the app's expected variable names)
- [ ] Update `[[addons]]` section in `config.md` reference

**Definition of done:** At least one new addon type (S3) shipped
with CLI commands, env var injection, tests, and documentation. MET in 0.5. Email addon is nice-to-have; it did not land in 0.6 and is now 0.7 work.

### Error message audit (improvement plan #9) — FOUNDATION DONE

- [x] Introduced `hop3.lib.diagnostics` with a `Diagnosis` dataclass
      and `abort_with_diagnosis()` helper producing
      `[Component] can't [action]: [reason]. [Hint].` messages with
      a troubleshooting bullet list
- [x] Unit tests for the diagnostics module (format, validation,
      `NoReturn` contract)
- [x] Converted the top deployment failure sites:
      - Docker builder (not-found, timeout)
      - Docker Compose deployer (not-found, timeout, command failure)
      - uWSGI worker config errors (`UWSGI_IDLE`, `UWSGI_ASYNCIO`)
      - Git-based deployer (prebuild/build/postbuild, no workers,
        no app detected)
      - Main deployer (config parse, start timeout, hook failure)
      - Addon provisioning
- [x] Updated existing tests that matched the old Abort strings
- [ ] Remaining next-batch sites: health checks, port allocation,
      nginx config errors
- [ ] Integration check: run `hop3-test system` against deliberately
      broken apps and verify the new messages surface

**Definition of done:** The `Diagnosis` pattern is in place and the
highest-traffic failure paths use it; next-batch sites (health, ports, nginx) can land in 0.5 or 0.6 as time allows.

### CLI DX pass (M3.6) — DONE (W16, ADR 036 M1-M8 shipped)

The "full refactor" previously deferred to 0.6 was actually executed across W16 (Apr 15–17) on the `cli-refact` branch and merged. ADR 036 moved from Draft to Accepted.

- [x] Colon→space command syntax migration (M1): `hop3 config:set`
      → `hop3 config set`. 71 server commands, 1033 tests green.
- [x] Namespace reorganization (M1b): `admin:user:*` → `user *`,
      `addons` → `addon`, verb normalization, `sbom` demoted.
- [x] Implicit app + sticky context (M2): 6-source resolution chain
      (`--app` → `$HOP3_APP` → `.hop3-app` → `hop3.toml [cli].app`
      → context → git remote), `hop3 use [app]`, `--why` flag.
- [x] Alias mechanism (M3): core + plugin + user aliases, disjoint
      union, `hop3 aliases` introspection, `--no-alias` bypass.
- [x] Help rendering (M4): categorized top-level, per-command D11
      order (USAGE → EXAMPLES → DESCRIPTION → SUBCOMMANDS),
      namespace-bare help, EXAMPLES mandatory on all commands.
- [x] Did-you-mean + structured no-app-resolved errors (M5).
- [x] Confirmations, summaries, secret handling (M6): `--confirm`
      typed-name, `--no-input`, stderr discipline, `--password-file`
      / `--stdin` secret inputs.
- [x] Exit codes harmonized to D16 table (M7): 11 codes including
      10 (confirmation declined), 130 (SIGINT).
- [x] Alias diagnostics, `--no-input` env bridge, app-name cache
      (M8).
- [x] Streaming `hop3 deploy` output (pre-W16).
- [x] `hop3 app info` clickable URL, `hop3 apps` sorted.

Test count trajectory: 1033 → 1218 passing across M1-M8.

### Web UI review (M3.7)

- [ ] Review all dashboard pages for broken links / stale data
- [ ] App creation: support Git URL input
- [ ] Environment variable editing: validate before save
- [ ] Ensure all CRUD operations work end-to-end

### Interim technical report review (M5.3) — DONE (W16)

TR-01 was refactored into proper technical-report form in W16: abstract, keywords, related work, system design, preliminary evaluation, threats to validity, references. Appendix E updated for ADR 039 Phase 1. App counts and Nix/ADR 008 content reflect current state.

- [x] Re-read TR-01 against 0.5 state
- [x] Nix section reflects ADR 008 (template-based generation, 8 templates, reproducibility tiers)
- [x] App counts updated (38 native + 32 Nix + 25 nix-gen + 42 Docker)
- [x] Security audit section reflects the 4 M3.8 fixes
- [x] Interim PDF rendered at `notes/reports/TR-01.pdf`
- [ ] Share with NGI reviewers for feedback

(Screencasts M5.6, paper benchmarks, and final paper submission are all deferred to 0.6 — see `release-plan-0.6.md`.)

### Server-side packaging-gap fixes — DONE (W16, Tier 1)

Surfaced from the 30-app packaging effort (G1–G7 gaps). Tier 1 landed in W16 as commit `2c3c698e` on devel:

- [x] **G1 — Postgres CREATE grants.** `plugins/postgresql/postgres.py`
      now grants `CREATE ON DATABASE` + `CREATE, USAGE ON SCHEMA
      public` to the per-app user so migrations can install trusted
      extensions (`pg_trgm`, `hstore`, …) on PG 15+. Plus a new
      `install_extensions()` method that runs
      `CREATE EXTENSION IF NOT EXISTS` as superuser for non-trusted
      extensions declared via `[[addons]].extensions` (bloom,
      adminpack). Unblocks BookWyrm; would have unblocked
      Funkwhale / Pretalx / Lemmy / Mastodon-on-fresh-install.
- [x] **G3 — Docker build timeout tier-aware.** Replaced hardcoded
      10-minute cap with a tier-keyed table (fast=5m, medium=10m,
      slow=20m, very-slow=30m) driven by `[build].tier`.
- [x] **G7 Phase 1 — Python toolchain (ADR 039).** Drops
      `--upgrade` from pip-install paths; adds `--no-dev` to
      `uv sync`; errors on both-files-present; detects Poetry-only
      pyprojects with actionable hint. Non-breaking; unblocks
      future Django catalogue apps. Phases 2-3 (explicit
      `[build.python].strategy`, lint rules, tutorial rewrite)
      deferred to 0.6.

Tier 2 (G2 `[build].packages`, G5 `nix-env-exports`) and Tier 3 (G4 Rust toolchain, G6 `node-npm-install`) remain open.

### New ADRs in 0.5 window

- **ADR 036 — CLI Ergonomics** — Accepted after M1–M8 shipped.
- **ADR 039 — Python Deploy Strategies** — Active, Phase 1 shipped.

### Tier-F fediverse packaging (new track, W16)

A dedicated Tier F for fediverse apps was added to the internal packaging priority list explicitly because NGI has been the primary funder of the fediverse ecosystem. W16 batch landed:

- [x] GoToSocial (3/4 variants — nix-gen deferred)
- [x] WriteFreely (3/4 — nix-gen deferred; hybrid nixpkgs+tarball)
- [x] Owncast (4/4 — `packages = ["ffmpeg"]`)

### Packaged apps — experience reports (M4.1-4)

20 draft reports already exist in `notes/experience-reports/`. This task converts them from descriptive drafts into real-world reports based on actual production deployments.

**Apps to deploy (in order, easiest first):**
1. Miniflux (RSS, single-user)
2. Gitea (Git hosting, used by team daily)
3. WordPress (CMS, MySQL)
4. Etherpad (collaborative editing)
5. NextCloud (file sync, most complex — MySQL + cron + storage)

**Per-app workflow:**
- [ ] Provision server (or reuse), configure DNS, deploy
- [ ] Add real content (import from existing instance if applicable)
- [ ] Use it daily; track issues
- [ ] After ~1 week: write experience report covering what worked,
      what broke, what would have helped

**Definition of done:** At least 5 apps running in production for 1+
week, 5 updated experience reports published. (Remaining 15 reports stay as drafts; finalised in 0.6.)

### Test suite green

App counts updated from post-W16 reality:
- [ ] All `test-apps-procfile/` passing
- [ ] All `test-apps-nix/` passing
- [ ] All `real-apps-native/` passing (target: 38/38; MediaWiki landed 2026-04-17; Pretalx + Redmine deferred)
- [ ] All `real-apps-nix/` passing (target: 30+/32)
- [ ] All `real-apps-nix-gen/` passing (target: 22+/25)
- [ ] All `real-apps-docker/` passing (target: 40+/42)

### Release mechanics — DONE (0.5.0 released 2026-06-08)

- [x] Merge `nix-builders` branch into `main`
- [x] Update version to 0.5.0 in all pyproject.toml
- [x] Write CHANGELOG entry
- [x] Tag 0.5.0
- [ ] Blog post: "Hop3 0.5: Nix Templates, 70+ Apps"

## Priority Order (if time runs short)

1. **Nix bad-app fixes (trivial batch)** — searxng, xwiki, matrix-synapse sed bug (~1 hour total, unblocks 3 apps)
2. **postgres.py supervisord fallback** — unblocks all 5 addon-needing nix apps in Docker CI
3. **Production deploys** — M4 reports need real data
4. **Web UI review** — M3.7
5. **Nix bad-app fixes (medium batch)** — hedgedoc, matrix-synapse libzstd, etherpad, cryptpad
6. **Interim tech report review** — reflect 0.5 state for NGI feedback
7. **Error message audit (next batch)** — health/ports/nginx
8. **Nix CI integration** — infrastructure polish
9. **Focalboard decision** — trivial cleanup

Done in earlier iterations: S3 addon (M3.1), multi-service ADR 038, diagnostics foundation + top failure sites, nix bad-app triage + installer infra fixes, **CLI DX refactor (ADR 036 M1-M8)**, **Tier-1 server-side packaging fixes (G1/G3/G7 + ADR 039 Phase 1)**, **interim TR-01 refactor**, **nix trivial-batch bad-app fixes**.

Moved to 0.6: paper benchmarks, screencasts (M5.6), final paper submission (M5.3 final).

## Risks

| Risk | Mitigation |
|------|------------|
| Benchmarks reveal Hop3 is slower than expected | Straightforward reporting; the paper's value is the architecture, not raw speed |
| Production deploys uncover blocker bugs | Triage: fix critical, defer rest |
| Screencast recording reveals UX issues | Note them for 0.6; record what works |
| External NGI security review delays | Submit findings early; don't block release on response |
| Time runs out before all done | Use priority order above; cut from the bottom |

## Definition of Done (whole release) — 0.5.0 RELEASED 2026-06-08

- [x] S3 addon shipped (M3.1 expansion)
- [x] All 0.5 security fixes shipped (M3.8 code done; external review
      is 0.7 work)
- [x] Multi-service ADR 038 written (implementation reslotted to 0.7 —
      not in the 0.6 changelog)
- [x] Diagnostics foundation + top failure sites use structured
      `Diagnosis` messages
- [x] CLI DX refactor (ADR 036 M1-M8) landed
- [x] ADR 039 Phase 1 (Python toolchain) landed
- [x] Tier-1 server-side packaging-gap fixes (G1/G3/G7) landed
- [x] Interim tech report refreshed (TR-01 in proper technical-report form)
- [x] Interim TR shared with NGI reviewers
- [ ] At least 3 production deployments running with reports (M4.1) —
      production traffic carried to 0.7
- [x] Nix runtime stabilised (bad apps triaged — W16 unblocked 3 trivial; medium batch carried forward)
- [ ] Focalboard decision executed
- [x] Test suite green
- [x] 0.5.0 tagged and announced
