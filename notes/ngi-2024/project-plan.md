# Project plan for the NGI project (#2024-04-365)

**Last reviewed:** 2026-06-21 (0.6 cut)

## T1 - Nix Build Plugins for Hop3

The project will enhance Hop3 by integrating the Nix package manager to provide reproducible environments and to improve build-time flexibility and reliability. This will expand the concept of "builder" in Hop3 to provide additional or alternative builders, all leveraging the Nix technology.

Deliverables include developing a Nix "native" builder for applications with an existing Nix expression, for instance when they are already in the Nixpkgs repository, to incorporate existing Nix expressions into Hop3's build workflow and metadata system. Additionally, the project will create or integrate Nix-based alternatives for applications lacking Nix configurations by encapsulating native build processes (e.g., pip, npm, mvn) using tools like Dream2nix, ensuring smooth integration with Hop3's build and deployment ecosystem.

### Milestone(s)

- [x] **M1.1** Nix "native" builder (for integrating apps described by a Nix expression)
  - NixBuilder plugin reads `hop3.nix`, runs `nix-build`, extracts `runtime.json`
  - 32 hand-crafted `hop3.nix` apps deployed and tested (as of 2026-04-18)
  - Static site support via nginx (absolute Nix store paths)

- [x] **M1.2** Nix alternatives to all the existing builders (at least: Python, Nodejs, Ruby, Go, Rust, Java) for "12 Factor App" like workflow
  - Template-based generation from `[nix]` section in `hop3.toml` (ADR 008, v0.6 Final)
  - 8 templates: `prebuilt-binary`, `prebuilt-archive`, `php-app`, `node-prebuilt`, `java-war`, `python-venv`, `nixpkgs-wrapper`, `ruby-bundler`
  - 25 template-generated apps validated (as of 2026-04-18)
  - `nix eject` command to materialize for customization
  - 119 unit tests for the generator
  - **Note:** We replaced Dream2nix/poetry2nix/node2nix with our own template approach after finding ecosystem tools didn't match our actual usage patterns. See ADR 008 v0.5 for rationale.

<!-- Note: the signed app catalog (ADR 049; `hop3 catalog refresh`, dashboard browse, `hop3-catalog validate`/`publish`) and the single-source server secret (ADR 048, HOP3_SECRET_KEY) shipped in 0.6; see M3.1/M3.6/M3.7 and CHANGES.md [0.6.0]. -->

## T2 - Nix Runtime

The project will extend Hop3 by integrating Nix as a powerful foundation for creating and managing runtime environments for application workers. This integration will ensure consistency, reproducibility, and reliability in how applications are executed, while providing robust isolation to minimize workload interference and enhance security. Nix will complement Hop3's existing and upcoming support for diverse execution environments, including lightweight Linux isolation, containers, lightweight VMs, full VMs, edge, IoT devices, and bare-metal setups. By offering Nix as an additional or alternative runtime, the platform will provide users with a versatile and future-proof solution tailored to various deployment scenarios.

### Milestone(s)

- [x] **M2.1** Specifications and Proof of Concept
  - NixBuilder plugin integrated into Hop3's plugin architecture (Pluggy hooks)
  - `BuildArtifact` with `RuntimeConfig` carries Nix store paths, env vars, workers
  - `runtime.json` format specifies workers, env, PATH for any Nix-built app

- [ ] **M2.2** Bêta implementation — **~80% done**
  - uWSGI deployer handles Nix artifacts (web, wsgi, static workers)
  - 32 hand-crafted + 25 template-generated apps running end-to-end
  - **Bad-app triage (W16):** searxng / xwiki / matrix-synapse fixed via template+sed cleanups; sonarqube and monica permanently deferred (bundled ES / Laravel-Mix incompatibility documented under `apps/bad/*/DEFERRED.md`).
  - **Remaining:** etherpad (needs clean retry deploy), hedgedoc (node_modules lost in Nix-store cp), cryptpad (npm install > 10-min timeout), listmonk (re-evaluate, may be viable via `pkgs.listmonk`), matrix-synapse libzstd `LD_LIBRARY_PATH` polish.

- [ ] **M2.3** Final release ("1.0") — **not started**
  - Needs: documentation polish, CI integration, release notes
  - Depends on M2.2 completion

## T3 - Security & Resilience

We will enhance Hop3's resilience and security by introducing robust features and tools. This includes integrating essential backing services like storage, email, and databases in alignment with the 12-Factor App methodology. Upgrade mechanisms will ensure seamless platform and application updates, with a focus on safe data migrations. Automated backups will enable reliable restoration and migration across servers or clusters, validated through resilience and migration tests. A comprehensive testing framework will include end-to-end deployment and runtime-specific canary tests to verify application health, and also that the whole application lifecycle is thoroughly tested. Security will be fortified with network-level firewalls and a Web Application Firewall (WAF) using tools like OWASP Core Ruleset and Coraza. We will redesign the current Command-Line Interface (CLI) optimizing UX for developers and devops, and create a basic web-based User Interface (UI) for non-technical users to interact with Hop3 visually.

### Milestone(s)

- [x] **M3.1** Backing services (storage, email…) — **mostly done** (email deferred to 0.7)
  - PostgreSQL, MySQL, Redis addons fully implemented with CLI commands
  - `addon create`, `addon attach`, `addon detach`, auto-provisioning from `[[addons]]` in hop3.toml
  - S3-compatible object storage addon shipped in 0.5 (MinIO backend with a plugin abstraction ready for a Garage swap in a future release)
  - **0.6 (shipped):** the full `addon <type> <verb>` operational surface (ad-hoc query, read-only diagnostics, clone, export/import dump streaming, restore/flush, exists, expose/unexpose, promote, endpoint, `hop3 tunnel`); plus per-app resource limits and volumes (ADR 046: memory/CPU caps for native + containerized apps shown in `hop3 app status`; bind + tmpfs volumes via the privileged daemon behind a default-deny allow-list)
  - W16: PostgreSQL addon now grants CREATE on the per-app DB + public schema (G1), and `[[addons]].extensions` installs non-trusted extensions (bloom, adminpack) as superuser
  - **Remaining gap:** Email addon (SMTP-relay design agreed, implementation deferred to 0.7)

- [ ] **M3.2** Upgrades (including data migrations) — **partial**
  - Alembic database migrations for Hop3's own schema
  - `hop3-deploy --local` for server upgrades during development
  - **Missing:** No `hop3 upgrade` command for production; no app-level upgrade orchestration

- [ ] **M3.3** Backups (including resilience and migration tests)
  - BackupManager with `backup:create`, `backup:restore`, `backup:list`, `backup:delete`, `backup:info`
  - Web UI for backup management
  - **Partial gap:** Migration tests (backup on server A, restore on server B) not automated

- [x] **M3.4** Testing framework and infrastructure
  - `hop3-test` CLI with Docker and SSH targets
  - Test discovery via `test.toml`, filtering by tier/priority/services
  - 118 apps across 6 test suites
  - Direct port testing, SSH curl, nginx testing for static apps
  - 599 unit + 245 integration + system + E2E tests

- [ ] **M3.5** Firewalls (network-level and WAF) — **network firewall done; WAF deferred to 0.7**
  - Network-level firewall + fixed-port registry shipped (ADR 045, Final, superseding ADR 040).
  - LeWAF (implements the OWASP Core Rule Set) static-WAF Phase 1 prototyped per ADR 033; 88 tests passing.
  - Network-level firewall design: see ADR 040 (port exposure) and ADR 041 (`hop3-rootd`, the kernel-boundary executor).
  - WAF integration (LeWAF / OWASP CRS, dynamic WAF, policy engine, observability) is carried to the 0.7 backlog.

- [x] **M3.6** CLI — **DONE** (W16; finalized in 0.6)
  - 73+ registered commands with `space`-separated naming (post ADR 036 M1 migration)
  - 0.6 completed the ADR 036 migration: the deprecated positional app argument was removed (app target is `--app <name>` only), and several commands were renamed with the old spellings kept as aliases (`launch`→`create`, `backup info`→`backup show`, `addon ps`→`addon activity`, `domains`→`domain`, `env migrate`→`app migrate`, account creation under `user add`).
  - SSH tunneling, JSON-RPC, streaming deploy output
  - Multi-server contexts, auto-authentication
  - ADR 036 (CLI Ergonomics) Accepted: colon→space syntax, implicit app + sticky context, aliases, categorized help with mandatory EXAMPLES, did-you-mean suggestions, confirmations / `--confirm=<name>` / `--no-input` / `--password-file`, D16 exit-code table (11 codes), alias diagnostics, app-name cache.
  - Test count 1033 → 1218 across M1–M8.

- [ ] **M3.7** Web UI (basic)
  - Dashboard with app management, addon management, backup management
  - Environment variable editing, log viewing
  - 14 HTML templates
  - 0.6: dashboard can browse the signed app catalog (ADR 049)
  - **Gap:** App creation from UI is basic; no Git URL deploy from web (deferred to 0.7); needs UI review

- [ ] **M3.8** Process outcomes of security audit and accessibility scan
  - Internal security audit completed (3 critical, 5 high, 8 medium, 6 low)
  - All 4 flagged fixes shipped: magic-link default username removed; rate-limiting on `/auth/login` + magic-link endpoint; bearer-token case insensitivity per RFC 7235; `HOP3_TOKEN_EXPIRY_HOURS` configurable session lifetime.
  - **Remaining:** external NGI security review (submit findings, await response).

## T4 - Packaged Applications

Package 20 popular or useful open-source applications to run on Hop3, covering a large range of functional domains, applications types and backing technologies. This will serve as progressive validation and demonstration of the other deliverables, but also provide robust products for end-users of the platform. This will also include writing the necessary declarative configurations, tests, and possibly patches, and documenting the process. Experience reports will be generated to capture any issues, challenges, or lessons learned from the packaging process, and will act as a guide for future similar efforts. This will be an iterative effort, in the sense that the initial packages will continue to evolve, if necessary, with additional or enhanced features of the platform.

### Milestone(s)

- [ ] **M4.1** - 5 first applications + experience reports — **done (configs, not production deployments)**
- [ ] **M4.2** - 5 next applications + experience reports — **done (configs, not production deployments)**
- [ ] **M4.3** - 5 next applications + experience reports — **done (configs, not production deployments)**
- [ ] **M4.4** - 5 last applications + experience reports — **done (configs, not production deployments)**

**Status (2026-04-18):** 38 native apps + 32 Nix apps + 25 Nix-gen apps + 42 Docker apps configured and tested via `hop3-test`. Covers: WordPress, Gitea, Forgejo, Miniflux, BookStack, Grafana, NextCloud, Matomo, Jenkins, Mattermost, LimeSurvey, Kanboard, Invoice Ninja, Focalboard, Vikunja, Wiki.js, Etherpad, HedgeDoc, Radicale, Adminer, Isso, SearXNG, Dolibarr, XWiki, Mastodon, Matrix Synapse, BookWyrm, Stirling-PDF, Vaultwarden, GoToSocial, WriteFreely, Owncast, Gatus, MediaWiki, and more.

**New in W16 (2026-04-14→18):** Tier-A Stirling-PDF (4/4), Tier-B Forgejo (4/4), Tier-A Vaultwarden (1/4, docker/native deferred pending Rust toolchain in installer), Tier-F GoToSocial (3/4), WriteFreely (3/4), Owncast (4/4), Tier-C Gatus (4/4), MediaWiki (2/4). Pretalx and Redmine attempted 2026-04-17, both deferred (pretalx wheel lacks pre-built Vite frontend; Redmine native bundler-env propagation to before-run scripts needs deeper fix).

**Gap:** Experience reports not written as standalone documents. Lessons learned are captured but not formatted as per-app reports. None of these apps deployed to production with real traffic yet. (A dozen of internal apps currently in production, though).

## T5 - Dissemination & Engagement

Effective dissemination is critical for the success of Hop3 as an Open Source platform, ensuring adoption, community contributions and recognition within the industry.

This task focuses on promoting Hop3 through an enriched website and blog with regular updates, comprehensive documentation for developers, administrators, and end-users, and a technical report or research paper highlighting project outcomes. It includes presenting at industry events like OW2Con, OSXP, FOSDEM, or NixCon to showcase progress and attract contributors. Additionally, videos, live office hours, and social media engagement will provide instructional content and real-time support, fostering a strong and active community around Hop3.

### Milestone(s)

- [x] **M5.1** Website, blog (structure & regular content updates)
  - hop3.cloud deployed with MkDocs
  - 11 blog posts (beta announcement, release notes, architecture posts)
  - Tutorials by language/framework

- [x] **M5.2** Documentation (for devs, admins, end-users)
  - User guide, installation guide, CLI reference, hop3.toml reference
  - Developer documentation (plugin development, architecture)

- [ ] **M5.3** Technical report and/or research paper — **~85% done**
  - TR-01 refactored into proper technical-report form in W16: abstract, keywords, related work, system design, preliminary evaluation, threats to validity, references. App counts and ADR 008 / 039 sections reflect current state.
  - TR-02 (second interim technical report) written for the 0.6 cycle, covering the 0.5 and 0.6 cycles (see `notes/reports/TR-02.md`).
  - Appendix E updated for new ADRs (036, 038, 039).
  - **Missing:** Benchmarks (control plane memory, deployment time, Nix closures, startup time). Cannot submit the final paper without quantitative evaluation.

- [x] **M5.4** Conference presentation or workshop
  - Hop3 talks done at OW2Con 2025, OSXP 2025, and OW2Con 2026 (a blog post for OW2Con 2026 is drafted under `docs/blog/posts/2026-06-ow2con.md`).

- [ ] **M5.6** Videos/screencasts — **not started**
  - Plan exists
  - Two screencasts planned: "Zero to Running App", "Dashboard Tour"
