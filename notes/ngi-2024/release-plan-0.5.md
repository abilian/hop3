# Hop3 0.5.0 Release Plan

**Target:** Early May 2026
**Theme:** Consolidation — make what we have solid and demonstrable
**Branch:** `main` (merge from `nix-builders`)
**Last updated:** 2026-04-11

## Goals

Version 0.5 closes the gaps that prevent demonstrating Hop3 to the NGI
reviewers. It does not add major new features — it makes existing
features reliable, documented, and presentable.

## Critical path

```
Paper benchmarks ──▶ Tech report review ──▶ Paper submission (M5.3)
   (4-5 days)            (1 day)
```

This is the longest blocking chain. Everything else can run in parallel.

## Scope

### Nix runtime stabilisation and completion (M2.2 + M2.3)

#### Triage `apps/bad/real-apps-nix-bad/` (8 apps) — TRIAGED

All 8 apps debugged on Docker target (2026-04-11). Root causes
identified for all; full report at `/tmp/nix-triage/findings.md`.

**Infrastructure bugs found and fixed (c65f5509):**
- Bundler silent name collision (`_has_systemd` in nix.py vs s3.py)
- `has_systemd()` false-positive in containers → shared
  `/proc/1/comm`-based helper in `common.py`
- Single-user nix never wrote `sandbox = relaxed` → `__noChroot`
  rejected
- Bundler now AST-detects top-level name collisions
- Test log writer missing `mkdir parents=True`

**Infrastructure bugs flagged, not yet fixed:**
- `postgres.py` has no supervisord fallback (Docker containers)
- hop3-server wraps `RepositoryError` as opaque "data processing"
  error on redeploys
- Test runner deploy-timeout doesn't kill orphaned nix-build

**Per-app triage:**

Trivial fixes (~1 hour total):
- [ ] **searxng** — `rev = "master"` non-reproducible → pin tag
- [ ] **xwiki** — unquoted heredoc → `$out` unexpanded at runtime
- [ ] **matrix-synapse** — sed `s|VENV|…|` mangles `VENV_LIB=`

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
- [ ] **sonarqube** — read-only Nix store + amd64-only + bundled
      ES + ~3GB RAM + source-available licensing. **Recommend drop.**

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
- [x] Documented `hop3 nix:eject` in CLI reference (`cli.md`) under
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

6 of 7 Nix apps converted from pre-built binaries to nixpkgs source
builds via the `nixpkgs-wrapper` template. Multi-arch support gained
(aarch64, ARM, RISC-V, etc.). See `plan-source-builds.md`.

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

The current addon set (PostgreSQL, MySQL, Redis) covered most
applications but left visible gaps for apps that need object
storage or email. The 0.5 goal was to add at least one; S3 shipped.

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
plan is to replace it with Garage (genuinely AGPL) in a future
release — the backend abstraction already exists to make the swap
a one-liner on the plugin side.

#### Email addon (stretch — can slip to 0.6)

- [ ] Design decision: SMTP relay config vs full mail server?
      Recommendation: SMTP relay only (point at user's existing
      provider) — running a mail server is out of scope for a PaaS.
- [ ] `addons:create email <name> --smtp-host <h> --smtp-user <u>`
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
with CLI commands, env var injection, tests, and documentation.
Email addon is nice-to-have; can slip to 0.6.

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
highest-traffic failure paths use it; next-batch sites (health,
ports, nginx) can land in 0.5 or 0.6 as time allows.

### CLI DX pass (M3.6)

- [ ] Audit and fix inconsistent app name parameter handling
- [x] `hop3 deploy` streaming output by default
- [ ] Actionable error messages for the 10 most common failures
      (covered by error message audit above)
- [x] `hop3 app:info` shows clickable URL
- [x] `hop3 apps` sorted alphabetically

(Full CLI DX refactor — consistent parameter ordering, granular exit
codes, JSON output, progress indicators — deferred to 0.6.)

### Web UI review (M3.7)

- [ ] Review all dashboard pages for broken links / stale data
- [ ] App creation: support Git URL input
- [ ] Environment variable editing: validate before save
- [ ] Ensure all CRUD operations work end-to-end

### Interim technical report review (M5.3)

The current TR-01 is an **interim** NGI progress report, not the
final paper. Final paper + benchmarks + submission are 0.6 work.
For 0.5 the goal is just to make sure the interim report reflects
0.5-era reality (ADR 008 shipped, source builds done, etc.).

- [ ] Re-read TR-01 with fresh eyes against the 0.5 state
- [ ] Update the Nix section to reflect ADR 008 and source builds
- [ ] Update the app count (28 native + 22 Nix + 20 nix-gen + 30
      Docker apps) and the reproducibility tier discussion
- [ ] Update the security audit section (4 fixes landed in 0.5)
- [ ] Generate updated interim PDF
- [ ] Share with NGI reviewers for feedback

(Screencasts M5.6, paper benchmarks, and final paper submission
are all deferred to 0.6 — see `release-plan-0.6.md`.)

### Packaged apps — experience reports (M4.1-4)

20 draft reports already exist in `notes/experience-reports/`.
This task converts them from descriptive drafts into real-world
reports based on actual production deployments.

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
week, 5 updated experience reports published. (Remaining 15 reports
stay as drafts; finalised in 0.6.)

### Test suite green

- [ ] All `test-apps-procfile/` passing
- [ ] All `test-apps-nix/` passing
- [ ] All `real-apps-native/` passing (28/28)
- [ ] All `real-apps-nix/` passing (target: 20+/22)
- [ ] All `real-apps-nix-gen/` passing (target: 18+/20)
- [ ] Docker apps: document known failures, skip in CI

### Release mechanics

- [ ] Merge `nix-builders` branch into `main`
- [ ] Update version to 0.5.0 in all pyproject.toml
- [ ] Write CHANGELOG entry
- [ ] Tag v0.5.0
- [ ] Blog post: "Hop3 0.5: Nix Templates, 70+ Apps"

## Priority Order (if time runs short)

1. **Nix bad-app fixes (trivial batch)** — searxng, xwiki, matrix-synapse
   sed bug (~1 hour total, unblocks 3 apps)
2. **postgres.py supervisord fallback** — unblocks all 5 addon-needing
   nix apps in Docker CI
3. **Production deploys** — M4 reports need real data
4. **Web UI review** — M3.7
5. **Nix bad-app fixes (medium batch)** — hedgedoc, matrix-synapse
   libzstd, etherpad, cryptpad
6. **Interim tech report review** — reflect 0.5 state for NGI feedback
7. **Error message audit (next batch)** — health/ports/nginx
8. **Nix CI integration** — infrastructure polish
9. **Focalboard decision** — trivial cleanup

Done in earlier iterations: S3 addon (M3.1), multi-service ADR 038,
diagnostics foundation + top failure sites, nix bad-app triage +
installer infra fixes.

Moved to 0.6: paper benchmarks, screencasts (M5.6), final paper
submission (M5.3 final).

## Risks

| Risk | Mitigation |
|------|------------|
| Benchmarks reveal Hop3 is slower than expected | Honest reporting; the paper's value is the architecture, not raw speed |
| Production deploys uncover blocker bugs | Triage: fix critical, defer rest |
| Screencast recording reveals UX issues | Note them for 0.6; record what works |
| External NGI security review delays | Submit findings early; don't block release on response |
| Time runs out before all done | Use priority order above; cut from the bottom |

## Definition of Done (whole release)

- [x] S3 addon shipped (M3.1 expansion)
- [x] All 0.5 security fixes shipped (M3.8 code done; external review
      is 0.6 work)
- [x] Multi-service ADR 038 written (implementation deferred to 0.6)
- [x] Diagnostics foundation + top failure sites use structured
      `Diagnosis` messages
- [ ] Interim tech report refreshed and shared with NGI reviewers
- [ ] At least 3 production deployments running with reports (M4.1)
- [ ] Nix runtime stabilised (bad apps triaged)
- [ ] Focalboard decision executed
- [ ] Test suite green
- [ ] v0.5.0 tagged and announced
