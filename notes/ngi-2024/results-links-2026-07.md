# NGI #2024-04-365 — Links to achieved results (per milestone) - Final Report

Status: draft. Last reconciled against the tree 2026-07-30. Still to add before submission: the `v0.7.0` release link, the asciinema URLs, the application gallery page, and the experience-reports PDF.
Date: XX July 2026

Evidence for the NLNet/NGI "verify these results" field, one entry per milestone. Documentation links resolve on <https://hop3.cloud/> (live at submission); code is on SourceHut (`sfermigier/hop3`), with a mirror on GitHUb (`abilian/hop3`); ADRs carry the design rationale.

## T1 — Nix Build Plugins

**M1.1 — Nix "native" builder (apps with a Nix expression)** ✅

- <https://hop3.cloud/guides/nix-deployment/> — guide: deploying an app from a `hop3.nix` expression
- <https://hop3.cloud/reference/nix/> — `hop3.nix` / `[nix]` reference
- <https://hop3.cloud/developers/adrs/006-nix-integration/> — design decision
- <https://git.sr.ht/~sfermigier/hop3/tree/main/packages/hop3-server/src/hop3/plugins/build/nix> — the NixBuilder (reads `hop3.nix`, runs `nix-build`, extracts `runtime.json`)
- <https://git.sr.ht/~sfermigier/hop3/tree/main/apps/real-apps-nix> — 31 hand-crafted `hop3.nix` apps, deployed & verified via `hop3-test` and `hop3-testlab`.

**M1.2 — Nix alternatives to existing builders (Python/Node/Ruby/Go/Rust/Java), 12-factor** ✅

- <https://hop3.cloud/developers/adrs/008-nix-builders-2/> — template-based generation from `[nix]` (8 templates incl. `nixpkgs-wrapper`, `python-venv`, `node-prebuilt`, `ruby-bundler`, `java-war`); rationale for replacing Dream2nix is inside
- <https://git.sr.ht/~sfermigier/hop3/tree/main/packages/hop3-server/src/hop3/plugins/build/nix/gen/templates> — generator, templates, `nix eject`
- <https://git.sr.ht/~sfermigier/hop3/tree/main/apps/real-apps-nix-gen> — 31 template-generated apps validated via `hop3-test`

## T2 — Nix Runtime

**M2.1 — Specifications & PoC** ✅

- <https://hop3.cloud/developers/adrs/035-build-artifacts/> — the runtime contract: `BuildArtifact`/`RuntimeConfig` carries Nix store paths, env, workers (`runtime.json`)
- <https://hop3.cloud/blog/posts/2026-03-build-artifact-pattern/> — blog explaining the build/run separation (the PoC mechanism)

**M2.2 — Beta implementation** ✅ — the 31 + 31 Nix apps above run end-to-end on the Nix runtime via the uWSGI deployer. The build/run contract, the closure pre-flight gate and the GC-root retention hardening all landed; what remains for 1.0 is dispositioning a handful of upstream apps that cannot be Nix-built.

- <https://git.sr.ht/~sfermigier/hop3/tree/main/apps/bad> — per-app `DEFERRED.md` notes documenting where an upstream app can't be Nix-built (each points at a platform gap)

**M2.3 — Final "1.0"** — *carried to 0.7.x*: the 20-app runtime pass with formal per-app dispositions, `make test-nix` nightly against a persisted `/nix/store`, the `[nix]` reference + reproducibility-tier polish, then the 1.0 cut.

## T3 — Security & Resilience

**M3.1 — Backing services** ✅ — *PostgreSQL/MySQL/Redis/S3 shipped; full operational command set + resource limits & volumes added in 0.6; email shipped as a swappable-backend addon*

- <https://hop3.cloud/guides/addons/> — guide: PostgreSQL, MySQL, Redis, S3/MinIO addons
- <https://hop3.cloud/developers/adrs/046-declarative-app-resources/> — declarative `[[addons]]`, generated secrets/env, and (Phase 2) `[limits]` resource caps + volumes
- <https://git.sr.ht/~sfermigier/hop3/tree/main/packages/hop3-server/src/hop3/plugins> — `postgresql/`, `mysql/`, `redis/`, `s3/`, `email/` plugins; 0.6 adds the `addon <type> <verb>` surface (query/diagnostics/clone/export-import/expose/promote/endpoint) and `hop3 tunnel`
- <https://hop3.cloud/developers/adrs/054-email-transport-and-notifications/> — **email as a backing service with a swappable backend**, symmetric with the database addon: the operator picks a backend once at server level (`relay` — provider or corporate smarthost, with EU-first provider profiles and DKIM auto-verify; `catch` — a dev sink, e2e-validated; `direct` — the box as its own MTA, shipping as preview), an app opts in by attaching an email addon, and the app-facing contract (`SMTP_*` pointing at a loopback endpoint) is stable across backends. The provider credential never enters an app's environment. Cert-renewal and deploy-failure notifications ride the active backend.

**M3.2 — Upgrades & data migrations** ✅

- <https://git.sr.ht/~sfermigier/hop3/tree/main/packages/hop3-server/src/hop3/orm/alembic> — Alembic schema migrations; upgrade deploy path hardened in 0.6 (migrations run on upgrade, venv preserved)
- `hop3 app upgrade --app <app>` — snapshot → redeploy + run the app's `before-run` migrations → health-verify → **automatic rollback to the pre-upgrade snapshot on any failure**; `hop3 app rollback` for operator-driven restore
- Server upgrade is the installer/deployer's job by decision (`local-notes/specs/upgrades.md`), and it is fail-loud: after migrating, the deployer confirms hop3-server actually answers before reporting success, and prints the exact revert command when it does not
- <https://git.sr.ht/~sfermigier/hop3/tree/main/packages/hop3-testing> — `hop3-test upgrade-chain`: install a baseline release on a fresh box, then upgrade in-place through a version chain, each version installed by **its own** installer (git worktree per tag), asserting every hop deploys and the schema stays readable. Green on both Docker and a fresh Hetzner VPS.

**M3.3 — Backups** — *cross-server migration test automated*

- <https://hop3.cloud/guides/backup-restore/> — backup/restore guide
- <https://hop3.cloud/developers/adrs/024-backup-restore-system/> — backup & restore system (Final)
- <https://git.sr.ht/~sfermigier/hop3/blob/main/packages/hop3-server/tests/c_e2e/test_backup_migration.py> — automated cross-server backup → restore test (backup on instance A, register and restore on instance B; plus negative-path cases)

**M3.4 — Testing framework & infrastructure** ✅

- <https://hop3.cloud/blog/posts/2026-06-how-hop3-is-tested/> — overview (start of a 5-part series)
- <https://hop3.cloud/developers/adrs/043-unified-testing-architecture/> — unified testing architecture
- <https://hop3.cloud/developers/adrs/044-nightly-test-lab/> — the nightly Test Lab
- <https://hop3.cloud/developers/testing-strategy/> — testing strategy doc
- <https://git.sr.ht/~sfermigier/hop3/tree/main/packages/hop3-testing> — the `hop3-test` runner (Docker/SSH/cloud targets; 100+ app and demos catalog)
- CI on SourceHut: <https://builds.sr.ht/~sfermigier/hop3/commits>
- Testlab demo: <https://testlab.hop3-dev.abilian.com/>

**M3.5 — Firewalls (network + WAF)** ✅ — *L3/L4 firewall + L7 WAF both shipped end-to-end*

- <https://hop3.cloud/developers/adrs/045-fixed-port-registry/> — exclusive host ports + firewall integration (Final)
- <https://hop3.cloud/developers/adrs/050-waf-l7-lewaf/> — L7 WAF design (LeWAF engine, OWASP Core Rule Set; Coraza as a future alternative)
- <https://hop3.cloud/developers/adrs/041-privileged-operations-agent/> — `hop3-rootd`, the kernel-boundary executor applying firewall/nginx changes
- <https://hop3.cloud/developers/adrs/040-network-firewall-and-port-exposure/> — firewall/port-exposure design
- <https://git.sr.ht/~sfermigier/hop3/tree/main/packages/hop3-server/src/hop3/waf> — WAF policy compiler + LeWAF engine (declarative `[waf]` → SecLang, compile-before-commit)
- <https://pypi.org/project/lewaf/> — **LeWAF 0.7.6**, the pure-Python OWASP-CRS engine written for this project and released standalone. A WAF-enabled app is fronted by `nginx → LeWAF proxy → uWSGI` on deploy (the proxy supervised as a uWSGI Emperor vassal, reaped on destroy); the app itself stays on loopback.
- Autonomous L7 bans per ADR 050 §4 — audit-stream scorer, `Ban` ORM, `hop3 waf bans` CLI, reconciled in-process. Docker e2e proves CRS blocking (SQLi / XSS / path-traversal / RCE) **and** the full ban loop over the real proxy chain, plus a false-positive pass.

**M3.6 — CLI (basic)** ✅

- <https://hop3.cloud/reference/cli/> — full CLI reference (~120 commands, space-separated, `--app` model)
- <https://hop3.cloud/developers/adrs/036-cli-ergonomics/> — CLI ergonomics & command surface
- <https://hop3.cloud/developers/adrs/042-cli-context-model/> — servers & project contexts
- <https://hop3.cloud/guides/cli-migration/> — migration from the old colon syntax
- <https://git.sr.ht/~sfermigier/hop3/tree/main/packages/hop3-cli>

**M3.7 — Web UI (basic)** — *review/polish in 0.7*

- <https://git.sr.ht/~sfermigier/hop3/tree/main/packages/hop3-server/src/hop3/server/controllers/dashboard> — dashboard controllers
- <https://git.sr.ht/~sfermigier/hop3/tree/main/packages/hop3-server/src/hop3/server/templates/dashboard> — 9 controllers, 21 templates (app/addon/backup management, env editing, log viewing, catalog browse + install)
- The dashboard installs and deploys from the signed catalog (0.6 could only browse it), and the per-app login check runs at the end of a dashboard deploy exactly as it does for a CLI one

**M3.8 — Security-audit & accessibility outcomes** — *three audit rounds processed in-house and all remediations shipped; third-party review applied for but never allocated; accessibility scan pending with M3.7*

Security review ran continuously through the project; most findings were fixed in the ordinary course of work. Three rounds are formalised below. A third-party review was applied for and followed up twice with NLnet without an auditor being allocated; rather than leave the milestone open indefinitely, the platform was audited in-house with tooling the project found and partly built, and the outcomes processed. We would still welcome that review and will act on its findings if it happens.

- <https://hop3.cloud/guides/security/> — **operator-facing security guide**: the account model, what the platform protects, what stays the operator's responsibility, pre-production checks
- <https://hop3.cloud/developers/security-model/> — **security model**: trust boundaries, actors, reviewed code patterns, and the procedure for running a review round
- <https://hop3.cloud/reference/policies/security-policy/> — published policy: disclosure channel (security@abilian.com), acknowledgement commitment, safe harbour
- <https://hop3.cloud/blog/posts/2026-05-security-audit/> — round 1 (published 2026-05-01): command-injection sweep, per-IP rate-limiting, RFC-7235 bearer matching, archive-extraction guards, configurable token lifetime
- <https://git.sr.ht/~sfermigier/hop3/tree/main/notes/security/report-2026-05.md> — round 2 (2026-05-03→08, five iterative rounds): a pre-authentication administrative takeover, magic-link scope confusion, anonymous self-registration, a production debug-mode leak, plus ~30 further fixes
- <https://git.sr.ht/~sfermigier/hop3/tree/main/notes/security/report-2026-07.md> — round 3 (2026-07): whole-repository automated audit (`letscode` + `vulnhunt`) with manual triage; installer input validation fixed the same day, and the control-plane tenancy model decided and documented rather than left implicit
- <https://hop3.cloud/developers/adrs/010-security-and-resilience/> — umbrella ADR mapping each security concern to its decision
- <https://hop3.cloud/developers/adrs/048-server-config-and-secret-storage/> — secret storage
- <https://hop3.cloud/developers/adrs/011-encryption/> — encryption posture

## T4 — Packaged Applications

**M4.1–M4.4 — 20 apps + experience reports** — *the 20 are packaged, published in the signed catalog, and verified by a real sign-in; the per-app reports are being rewritten to that bar*

The twenty that constitute the deliverable are the **signed catalog**: BookStack, Bugsink, Dolibarr, Easy!Appointments, Forgejo, Gitea, Invoice Ninja, Isso, Kanboard, Keycloak, LimeSurvey, Matomo, Mattermost, Miniflux, Nextcloud, Paheko, Radicale, Uptime Kuma, Vikunja, WordPress.

- **The verification bar changed, and this is the substantive M4 result.** "Working" no longer means an HTTP 200. Every catalog app ships a `check.py` (required to publish) that **signs in through the app's own authentication** with the credential Hop3 generated and confirms a wrong password is refused. It runs at the end of *every* deploy, dashboard included, and on demand via `hop3 app check --app <app>`. An app can declare a `[probe]` account — Hop3-owned, non-privileged, password rotated by Hop3 — so the check survives an operator changing the admin password.
- **It is reproducible rather than anecdotal.** `hop3-catalog/scripts/check-catalog.py` runs list → install → login-check → destroy for all twenty against a `hop3-deploy-server --provider hetzner --clean` OS rebuild, and exits non-zero on any failure. The 2026-07-27/28 acceptance campaign installed all twenty by hand through the Web UI first, root-causing every failure to a platform class and fixing it there (23 commits): HTTPS-by-default redirect (three apps' `Secure` cookies made sign-in loop over plain HTTP), PHP's single-threaded built-in server deadlocking against its own only worker, a failed install that could not be retried, `app credentials` showing a password for an account that was never created.
- <https://git.sr.ht/~sfermigier/hop3/tree/main/apps/real-apps-native> — 40 native-toolchain app configs
- <https://git.sr.ht/~sfermigier/hop3/tree/main/apps/real-apps-nix> — 31 hand-crafted Nix apps
- <https://git.sr.ht/~sfermigier/hop3/tree/main/apps/real-apps-nix-gen> — 31 template-generated Nix apps
- <https://git.sr.ht/~sfermigier/hop3/tree/main/apps/real-apps-docker> — 52 Docker app configs
- <https://hop3.cloud/guides/packaging-applications/> — how an app is described + tested
- <https://hop3.cloud/developers/adrs/049-catalog-distribution/> — the signed catalog; <https://hop3.cloud/developers/adrs/056-app-admin-credentials/> — generated admin credentials
- Wider coverage beyond the twenty incl. Grafana, Mastodon, Matrix Synapse, Vaultwarden, Jenkins, Wiki.js, SearXNG, Stirling-PDF, … each verified via `hop3-test`. Platform-gap findings captured per deferred app under `apps/bad/*/DEFERRED.md`.
- <https://git.sr.ht/~sfermigier/hop3/tree/main/notes/experience-reports> — the per-app experience reports *(being rewritten against the sign-in bar; 5 catalog apps still to cover)*

## T5 — Dissemination & Engagement

**M5.1 — Website & blog** ✅

- <https://hop3.cloud/> and <https://hop3.cloud/blog/> — 23 posts (release notes, architecture, security, the 5-part testing series, a "migrating from X" series, conference write-ups)

**M5.2 — Documentation (devs/admins/end-users)** ✅

- <https://hop3.cloud/guides/> · <https://hop3.cloud/reference/> · <https://hop3.cloud/developers/> · <https://hop3.cloud/tutorials/> — and 60 published ADRs at <https://hop3.cloud/developers/adrs/>

**M5.3 — Technical report / paper** — *drafted end-to-end; benchmarks measured; awaiting repeat runs and submission*

- <https://git.sr.ht/~sfermigier/hop3/blob/main/notes/reports/TR-01.md> — first interim technical report (draft)
- <https://git.sr.ht/~sfermigier/hop3/blob/main/notes/reports/TR-02.md> — second interim technical report (draft)
- <https://git.sr.ht/~sfermigier/hop3/tree/main/notes/benchmarks> — **the measurement data**, tracked as JSONL beside a committed `protocol.yaml` and regenerated into the paper's tables by `hop3-bench report` (no figure in the paper is hand-typed). Headline results: control-plane **7.8× lighter than K3s** like-for-like (185 vs 1441 MB PSS); an 80-cell deploy matrix at 71/80 with median deploy 98 s native / 110 s nix / 116 s nix-gen / **163 s docker**, i.e. the Nix paths land within 12–18% of native and 1.4–1.5× faster than Docker; and **30/30 template-generated recipes bit-for-bit reproducible**. Every cell is currently n=1, so the evaluation is labelled preliminary until the repeat runs land.
- <https://git.sr.ht/~sfermigier/hop3/tree/main/packages/hop3-tooling> — the `hop3-bench` harness itself (probes, parsers, report generation), unit-tested independently of the runs

**M5.4 — Conference presentation / workshop** ✅

- <https://hop3.cloud/blog/posts/2025-06-ow2con/> — Hop3 at OW2Con 2025
- <https://hop3.cloud/blog/posts/2025-12-osxp/> — Hop3 at OSXP 2025
- <https://hop3.cloud/blog/posts/2026-06-ow2con/> — Hop3 at OW2Con 2026

**M5.6 — Videos / screencasts** — *68 recorded; publication pending*

- <https://git.sr.ht/~sfermigier/hop3/tree/main/screencasts> — **68 asciicasts** (33 demos + 35 tutorials). Each is a recording of a real run, not a staged reenactment: the demos and tutorials are executable and double as regression tests, so a screencast that would mislead is one that fails CI first.
- <https://git.sr.ht/~sfermigier/hop3/tree/main/demos> — the 36 scripted demos behind them (walkthrough + screencast source + regression test)
- *To add before submission:* the asciinema.org URLs, the site + PeerTube embeds, and the two narrated walkthroughs ("Zero to Running App", "Dashboard Tour").
