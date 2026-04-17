# Project plan for the NGI project (#2024-04-365)

**Last reviewed:** 2026-04-09

## T1 - Nix Build Plugins for Hop3

The project will enhance Hop3 by integrating the Nix package manager to provide reproducible environments and to improve build-time flexibility and reliability. This will expand the concept of "builder" in Hop3 to provide additional or alternative builders, all leveraging the Nix technology.

Deliverables include developing a Nix "native" builder for applications with an existing Nix expression, for instance when they are already in the Nixpkgs repository, to incorporate existing Nix expressions into Hop3's build workflow and metadata system. Additionally, the project will create or integrate Nix-based alternatives for applications lacking Nix configurations by encapsulating native build processes (e.g., pip, npm, mvn) using tools like Dream2nix, ensuring smooth integration with Hop3's build and deployment ecosystem.

### Milestone(s)

- [x] **M1.1** Nix "native" builder (for integrating apps described by a Nix expression)
  - NixBuilder plugin reads `hop3.nix`, runs `nix-build`, extracts `runtime.json`
  - 22 hand-crafted `hop3.nix` apps deployed and tested
  - Static site support via nginx (absolute Nix store paths)

- [x] **M1.2** Nix alternatives to all the existing builders (at least: Python, Nodejs, Ruby, Go, Rust, Java) for "12 Factor App" like workflow
  - Template-based generation from `[nix]` section in `hop3.toml` (ADR 008)
  - 8 templates: `prebuilt-binary`, `prebuilt-archive`, `php-app`, `node-prebuilt`, `java-war`, `python-venv`, `nixpkgs-wrapper`, `ruby-bundler`
  - 20 template-generated apps validated
  - `nix:eject` command to materialize for customization
  - 119 unit tests for the generator
  - **Note:** We replaced Dream2nix/poetry2nix/node2nix with our own template approach after finding ecosystem tools didn't match our actual usage patterns. See ADR 008 v0.5 for rationale.

## T2 - Nix Runtime

The project will extend Hop3 by integrating Nix as a powerful foundation for creating and managing runtime environments for application workers. This integration will ensure consistency, reproducibility, and reliability in how applications are executed, while providing robust isolation to minimize workload interference and enhance security. Nix will complement Hop3's existing and upcoming support for diverse execution environments, including lightweight Linux isolation, containers, lightweight VMs, full VMs, edge, IoT devices, and bare-metal setups. By offering Nix as an additional or alternative runtime, the platform will provide users with a versatile and future-proof solution tailored to various deployment scenarios.

### Milestone(s)

- [x] **M2.1** Specifications and Proof of Concept
  - NixBuilder plugin integrated into Hop3's plugin architecture (Pluggy hooks)
  - `BuildArtifact` with `RuntimeConfig` carries Nix store paths, env vars, workers
  - `runtime.json` format specifies workers, env, PATH for any Nix-built app

- [ ] **M2.2** Bêta implementation — **~50% done**
  - uWSGI deployer handles Nix artifacts (web, wsgi, static workers)
  - 22 hand-crafted + 20 template-generated apps running end-to-end
  - **Remaining:** ~8 apps in `real-apps-nix-bad/` that need fixes (etherpad, hedgedoc, cryptpad, searxng, listmonk, matrix-synapse, sonarqube, xwiki). Some may require new templates or Nix packaging effort.

- [ ] **M2.3** Final release ("1.0") — **not started**
  - Needs: documentation polish, CI integration, release notes
  - Depends on M2.2 completion

## T3 - Security & Resilience

We will enhance Hop3's resilience and security by introducing robust features and tools. This includes integrating essential backing services like storage, email, and databases in alignment with the 12-Factor App methodology. Upgrade mechanisms will ensure seamless platform and application updates, with a focus on safe data migrations. Automated backups will enable reliable restoration and migration across servers or clusters, validated through resilience and migration tests. A comprehensive testing framework will include end-to-end deployment and runtime-specific canary tests to verify application health, and also that the whole application lifecycle is thoroughly tested. Security will be fortified with network-level firewalls and a Web Application Firewall (WAF) using tools like OWASP Core Ruleset and Coraza. We will redesign the current Command-Line Interface (CLI) optimizing UX for developers and devops, and create a basic web-based User Interface (UI) for non-technical users to interact with Hop3 visually.

### Milestone(s)

- [ ] **M3.1** Backing services (storage, email…)
  - PostgreSQL, MySQL, Redis addons fully implemented with CLI commands
  - `addons:create`, `addons:attach`, `addons:detach`, auto-provisioning from `[[addons]]` in hop3.toml
  - **Partial gap:** No S3/object storage or email addon yet (database services only)

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

- [ ] **M3.5** Firewalls (network-level and WAF) — **not started**
  - LeWAF (Coraza-based) evaluated but no integration code
  - Planned for May 2026

- [ ] **M3.6** CLI (basic)
  - 73 registered commands covering all operations
  - SSH tunneling, JSON-RPC, streaming deploy output
  - Multi-server contexts, auto-authentication
  - **Gap**: But DX is clunky -> needs refactor

- [ ] **M3.7** Web UI (basic)
  - Dashboard with app management, addon management, backup management
  - Environment variable editing, log viewing
  - 14 HTML templates
  - **Gap:** App creation from UI is basic; no Git URL deploy from web; needs UI review

- [ ] **M3.8** Process outcomes of security audit and accessibility scan
  - Internal security audit completed (3 critical, 5 high, 8 medium, 6 low)
  - 4 fixes outstanding (magic link default, rate limiting, bearer token case, session lifetime)
  - Needs to start interacting with the NGI team

## T4 - Packaged Applications

Package 20 popular or useful open-source applications to run on Hop3, covering a large range of functional domains, applications types and backing technologies. This will serve as progressive validation and demonstration of the other deliverables, but also provide robust products for end-users of the platform. This will also include writing the necessary declarative configurations, tests, and possibly patches, and documenting the process. Experience reports will be generated to capture any issues, challenges, or lessons learned from the packaging process, and will act as a guide for future similar efforts. This will be an iterative effort, in the sense that the initial packages will continue to evolve, if necessary, with additional or enhanced features of the platform.

### Milestone(s)

- [ ] **M4.1** - 5 first applications + experience reports — **done (configs, not production deployments)**
- [ ] **M4.2** - 5 next applications + experience reports — **done (configs, not production deployments)**
- [ ] **M4.3** - 5 next applications + experience reports — **done (configs, not production deployments)**
- [ ] **M4.4** - 5 last applications + experience reports — **done (configs, not production deployments)**

**Status:** 28 native apps + 22 Nix apps + 20 Nix-gen apps + 30 Docker apps configured and tested via `hop3-test`. Covers: WordPress, Gitea, Miniflux, BookStack, Grafana, NextCloud, Matomo, Jenkins, Mattermost, LimeSurvey, Kanboard, Invoice Ninja, Focalboard, Vikunja, Wiki.js, Etherpad, HedgeDoc, Radicale, Adminer, Isso, SearXNG, Dolibarr, Monica, XWiki, SonarQube, Mastodon, Matrix Synapse, and more.

**Gap:** Experience reports not written as standalone documents. Lessons learned are captured but not formatted as per-app reports. None of these apps deployed to production with real traffic yet. (A dozen of internal apps currently in prodcution, though).

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

- [ ] **M5.3** Technical report and/or research paper — **~60% done**
  - Paper drafted with Promise Theory agent model, hop3.toml specification, 28-app evaluation, competitor comparison
  - **Missing:** Benchmarks (control plane memory, deployment time, Nix closures, startup time). Cannot submit without quantitative evaluation.

- [x] **M5.4** Conference presentation or workshop — **partial**
  - Hop3 talks already done at OW2Con 2025, OSXP 2025, and scheduled for OW2Con 2026

- [ ] **M5.6** Videos/screencasts — **not started**
  - Plan exists
  - Two screencasts planned: "Zero to Running App", "Dashboard Tour"
