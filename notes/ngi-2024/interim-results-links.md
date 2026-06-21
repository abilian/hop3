# NGI #2024-04-365 — Links to achieved results (per milestone)

Evidence for the NLNet/NGI "verify these results" field, one entry per milestone. Documentation links resolve on <https://hop3.cloud/> (live at submission); code is on GitHub (`abilian/hop3`); ADRs carry the design rationale. Partial / not-yet-started milestones are marked plainly so reviewers aren't sent after results that don't exist yet.

## T1 — Nix Build Plugins

**M1.1 — Nix "native" builder (apps with a Nix expression)**

- <https://hop3.cloud/guides/nix-deployment/> — guide: deploying an app from a `hop3.nix` expression
- <https://hop3.cloud/reference/nix/> — `hop3.nix` / `[nix]` reference
- <https://hop3.cloud/developers/adrs/006-nix-integration/> — design decision
- <https://github.com/abilian/hop3/tree/main/packages/hop3-server/src/hop3/plugins/build/nix> — the NixBuilder (reads `hop3.nix`, runs `nix-build`, extracts `runtime.json`)
- <https://github.com/abilian/hop3/tree/main/apps/real-apps-nix> — 34 hand-crafted `hop3.nix` apps, deployed & verified via `hop3-test`

**M1.2 — Nix alternatives to existing builders (Python/Node/Ruby/Go/Rust/Java), 12-factor**

- <https://hop3.cloud/developers/adrs/008-nix-builders-2/> — template-based generation from `[nix]` (8 templates incl. `nixpkgs-wrapper`, `python-venv`, `node-prebuilt`, `ruby-bundler`, `java-war`); rationale for replacing Dream2nix is inside
- <https://github.com/abilian/hop3/tree/main/packages/hop3-server/src/hop3/plugins/build/nix/gen/templates> — generator, templates, `nix eject`
- <https://github.com/abilian/hop3/tree/main/apps/real-apps-nix-gen> — 31 template-generated apps validated via `hop3-test`

## T2 — Nix Runtime

**M2.1 — Specifications & PoC**

- <https://hop3.cloud/developers/adrs/009-nix-runtime/> — the Nix-runtime specification
- <https://hop3.cloud/developers/adrs/035-build-artifacts/> — the runtime contract: `BuildArtifact`/`RuntimeConfig` carries Nix store paths, env, workers (`runtime.json`)
- <https://hop3.cloud/blog/posts/2026-03-build-artifact-pattern/> — blog explaining the build/run separation (the PoC mechanism)

**M2.2 — Beta (≈90%; a few upstream apps deferred)** — the 34 + 31 Nix apps above run end-to-end on the Nix runtime via the uWSGI deployer.

- <https://github.com/abilian/hop3/tree/main/apps/bad> — per-app `DEFERRED.md` notes documenting where an upstream app can't be Nix-built (each points at a platform gap)

**M2.3 — Final "1.0"** — *in progress, depends on M2.2* (docs polish, CI, release notes).

## T3 — Security & Resilience

**M3.1 — Backing services** — *S3/MinIO shipped in 0.5.0; email/SMTP addon deferred to 0.7*

- <https://hop3.cloud/guides/addons/> — guide: PostgreSQL, MySQL, Redis, S3/MinIO addons
- <https://hop3.cloud/developers/adrs/046-declarative-app-resources/> — declarative `[[addons]]`, generated secrets/env
- <https://github.com/abilian/hop3/tree/main/packages/hop3-server/src/hop3/plugins> — `postgresql/`, `mysql/`, `redis/`, `s3/` plugins

**M3.2 — Upgrades & data migrations** — *partial*

- <https://github.com/abilian/hop3/tree/main/packages/hop3-server/src/hop3/orm/alembic> — Alembic schema migrations; upgrade deploy path hardened in 0.6 (migrations run on upgrade, venv preserved). Production `hop3 upgrade` command planned for 0.7.

**M3.3 — Backups** — *cross-server migration test automated*

- <https://hop3.cloud/guides/backup-restore/> — backup/restore guide
- <https://hop3.cloud/developers/adrs/024-backup-restore-system/> — backup & restore system (Final)
- <https://github.com/abilian/hop3/blob/main/packages/hop3-server/tests/c_e2e/test_backup_migration.py> — automated cross-server backup → restore test (backup on instance A, register and restore on instance B; plus negative-path cases)

**M3.4 — Testing framework & infrastructure** ✅

- <https://hop3.cloud/blog/posts/2026-06-how-hop3-is-tested/> — overview (start of a 5-part series)
- <https://hop3.cloud/developers/adrs/043-unified-testing-architecture/> — unified testing architecture
- <https://hop3.cloud/developers/adrs/044-nightly-test-lab/> — the nightly Test Lab
- <https://hop3.cloud/developers/testing-strategy/> — testing strategy doc
- <https://github.com/abilian/hop3/tree/main/packages/hop3-testing> — the `hop3-test` runner (Docker/SSH/cloud targets; 100+ app catalog)

**M3.5 — Firewalls (network + WAF)** — *network firewall done; WAF Phase 1*

- <https://hop3.cloud/developers/adrs/045-fixed-port-registry/> — exclusive host ports + firewall integration (Final)
- <https://hop3.cloud/developers/adrs/041-privileged-operations-agent/> — `hop3-rootd`, the kernel-boundary executor applying firewall/nginx changes
- <https://hop3.cloud/developers/adrs/040-network-firewall-and-port-exposure/> — firewall/port-exposure design
- <https://github.com/abilian/hop3/tree/main/packages/hop3-rootd> — the privileged executor (firewall ops). *WAF (Coraza / OWASP-CRS) integration in the 0.7 backlog.*

**M3.6 — CLI (basic)** ✅

- <https://hop3.cloud/reference/cli/> — full CLI reference (~120 commands, space-separated, `--app` model)
- <https://hop3.cloud/developers/adrs/036-cli-ergonomics/> — CLI ergonomics & command surface
- <https://hop3.cloud/developers/adrs/042-cli-context-model/> — servers & project contexts
- <https://hop3.cloud/guides/cli-migration/> — migration from the old colon syntax
- <https://github.com/abilian/hop3/tree/main/packages/hop3-cli>

**M3.7 — Web UI (basic)** — *review/polish + Git-URL deploy in 0.7*

- <https://github.com/abilian/hop3/tree/main/packages/hop3-server/src/hop3/server/controllers/dashboard> — dashboard controllers
- <https://github.com/abilian/hop3/tree/main/packages/hop3-server/src/hop3/server/templates/dashboard> — 20 templates (app/addon/backup management, env editing, log viewing)

**M3.8 — Security-audit & accessibility outcomes** — *external NGI review + accessibility scan pending*

- <https://hop3.cloud/blog/posts/2026-05-security-audit/> — internal audit: findings and fixes (command-injection sweep, per-IP rate-limiting, RFC-7235 bearer matching, archive-extraction guards, configurable token lifetime)
- <https://hop3.cloud/developers/adrs/048-server-config-and-secret-storage/> — secret storage
- <https://hop3.cloud/developers/adrs/011-encryption/> — encryption posture

## T4 — Packaged Applications

**M4.1–M4.4 — 20 apps + experience reports** — *well past 20 configured & tested; standalone per-app reports being formatted; production-traffic deployments in progress*

- <https://github.com/abilian/hop3/tree/main/apps/real-apps-native> — 41 native-toolchain app configs
- <https://github.com/abilian/hop3/tree/main/apps/real-apps-nix> — 34 hand-crafted Nix apps
- <https://github.com/abilian/hop3/tree/main/apps/real-apps-nix-gen> — 31 template-generated Nix apps
- <https://hop3.cloud/guides/packaging-applications/> — how an app is described + tested
- Coverage incl. WordPress, Gitea/Forgejo, Nextcloud, Matomo, Grafana, Mastodon, Matrix Synapse, Vaultwarden, BookStack, … each verified via `hop3-test`. Platform-gap findings captured per deferred app under `apps/bad/*/DEFERRED.md`.

## T5 — Dissemination & Engagement

**M5.1 — Website & blog** ✅

- <https://hop3.cloud/> and <https://hop3.cloud/blog/> — 22 posts (release notes, architecture, security, the 5-part testing series, a "migrating from X" series)

**M5.2 — Documentation (devs/admins/end-users)** ✅

- <https://hop3.cloud/guides/> · <https://hop3.cloud/reference/> · <https://hop3.cloud/developers/> · <https://hop3.cloud/tutorials/> — and 49 published ADRs at <https://hop3.cloud/developers/adrs/>

**M5.3 — Technical report / paper** — *≈75%; benchmarks pending*

- <https://github.com/abilian/hop3/blob/main/notes/reports/TR-01.md> — first interim technical report
- <https://github.com/abilian/hop3/blob/main/notes/reports/TR-02.md> — second interim technical report

**M5.4 — Conference presentation / workshop**

- <https://hop3.cloud/blog/posts/2025-06-ow2con/> — Hop3 at OW2Con 2025
- <https://hop3.cloud/blog/posts/2025-12-osxp/> — Hop3 at OSXP 2025 (OW2Con 2026 scheduled)

**M5.6 — Videos / screencasts** — *not yet recorded*

- <https://github.com/abilian/hop3/tree/main/demos> — 34 scripted demos (walkthrough + screencast source + regression test) as the basis; two screencasts ("Zero to Running App", "Dashboard Tour") to follow.
