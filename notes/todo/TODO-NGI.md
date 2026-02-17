# TODO for the NGI Project

Detailed breakdown of the work items and deliverables, based on the MOU for the "Nix Integration for Hop3" project.

**Last Updated:** 2026-02-17

## Timeline Summary

| Task | Original Target | Revised Target | Status |
|------|-----------------|----------------|--------|
| **T1: Nix Build Plugins** | Q1 2026 | Q1 2026 | Not Started |
| **T2: Nix Runtime** | Q1 2026 | Q1 2026 | Not Started |
| **T3: Security & Resilience** | Q4 2025 | Q1 2026 | 6/8 Complete (75%) |
| **T4: Packaged Applications** | Q4 2025 | Q1 2026 | 0/20 Complete (0%) |
| **T5: Dissemination & Engagement** | Q4 2025 | Q1 2026 | 3/5 Complete (60%) |

**Note:** Non-Nix items (T3, T4, T5) were not completed in Q4 2025 and are now being completed in Q1 2026. See `local-notes/PLAN-2026-Q1.md` for detailed schedule.

## TOC

<!-- toc -->

- [T1: Nix Build Plugins for Hop3](#t1-nix-build-plugins-for-hop3)
- [T2: Nix Runtime](#t2-nix-runtime)
- [T3: Security & Resilience](#t3-security--resilience)
- [T4: Packaged Applications](#t4-packaged-applications)
  * [M4.1 - First 5 Applications](#m41---first-5-applications)
  * [M4.2 - Next 5 Applications](#m42---next-5-applications)
  * [M4.3 - Next 5 Applications](#m43---next-5-applications)
  * [M4.4 - Last 5 Applications](#m44---last-5-applications)
- [T5: Dissemination & Engagement](#t5-dissemination--engagement)

<!-- tocstop -->

## T1: Nix Build Plugins for Hop3

**Target:** Q1 2026
**Status:** Not Started

**Objective:** This task focuses on enhancing Hop3 by integrating the Nix package manager to create reproducible build environments and improve flexibility.

**Deliverables:**
* **M1.1 Nix "native" builder:** ⏳ NOT STARTED
  - A builder for applications that already have a Nix expression, integrating them into Hop3's workflow.
* **M1.2 Nix alternatives to existing builders:** ⏳ NOT STARTED
  - Nix-based alternatives for builders such as Python, Nodejs, Ruby, Go, Rust, and Java, following a "12 Factor App" like workflow.

## T2: Nix Runtime

**Target:** Q1 2026
**Status:** Not Started

**Objective:** To extend Hop3 by using Nix to create and manage application runtime environments, ensuring consistency and reproducibility.

**Deliverables:**
* **M2.1 Specifications and Proof of Concept:** ⏳ NOT STARTED
  - Initial design and feasibility demonstration of the Nix-based runtime.
* **M2.2 Bêta implementation:** ⏳ NOT STARTED
  - A functional beta version of the Nix runtime integration.
* **M2.3 Final release ("1.0"):** ⏳ NOT STARTED
  - The stable, production-ready version of the Nix runtime.

## T3: Security & Resilience

**Target:** Q1 2026 (carried from Q4 2025)
**Status:** 6/8 milestones complete (75%)

**Objective:** To improve the security and resilience of Hop3 by adding robust features and tools.

**Deliverables:**
* **M3.1 Backing services:** ✅ **COMPLETED** (2025-11-12)
  - [x] PostgreSQL service plugin with encrypted credentials (Fernet AEAD)
  - [x] Redis service plugin with connection management
  - [x] MySQL service plugin (added 2025-12-16)
  - [x] Service credential persistence in database
  - [x] Backup/restore integration for services

* **M3.2 Upgrades:** ✅ **COMPLETED** (2025-11-13)
  - [x] Alembic database migration system implemented
  - [x] Automatic migrations on server startup
  - [x] Rollback capability for schema changes
  - [x] Safe production upgrades enabled

* **M3.3 Backups:** ✅ **COMPLETED** (2025-11-13)
  - [x] Full backup/restore system with service data
  - [x] SHA256 checksums for verification
  - [x] Fail-fast behavior (backup fails if services cannot be backed up)
  - [x] 46 tests (18 unit + 9 E2E + 19 integration)

* **M3.4 Testing framework and infrastructure:** ✅ **COMPLETED** (2025-11-24, updated 2026-02-17)
  - [x] 638 tests across 4 layers (361 unit, 247 integration, 13 system, 17 E2E)
  - [x] 100% pass rate for unit/integration/system tests
  - [x] CI automation with GitHub Actions
  - [x] Docker-based E2E test infrastructure
  - [x] Pluggy+Dishka DI testing patterns
  - [x] Unified test runner (`hop3-test` CLI)
  - [x] Plugin-based health checks (2026-02-17)

* **M3.5 Firewalls:** ⚠️ **IN PROGRESS**
  - [ ] Network-level firewalls configuration (nftables)
  - [ ] Web Application Firewall (WAF) integration (ModSecurity)
  - [ ] Production testing and verification

* **M3.6 CLI (basic):** ✅ **COMPLETED** (2025-11-08)
  - [x] Rich CLI with color formatting
  - [x] Confirmation prompts for destructive operations
  - [x] Message type conventions (info, warning, error, success)
  - [x] 30 CLI tests passing

* **M3.7 Web UI (basic):** ✅ **COMPLETED** (2025-11-24)
  - [x] Production-ready dashboard with Litestar
  - [x] Server-Sent Events (SSE) log streaming
  - [x] Service management pages
  - [x] Backup UI (list, restore, delete)
  - [x] Dashboard view tests passing (100%)
  - [x] Guard-based authentication

* **M3.8 Process outcomes of security audit:** ⚠️ **IN PROGRESS**
  - [x] JWT token revocation implemented (2025-11-13)
  - [x] Token tampering protection
  - [x] SQL injection prevention
  - [x] Hardcoded password removal
  - [x] Plugin-based health checks for addons (2026-02-17)
  - [x] `hop3 system:check` command (2026-02-17)
  - [ ] Formal security audit
  - [ ] Accessibility scan
  - [ ] Production verification of all security measures

## T4: Packaged Applications

**Target:** Q1 2026 (carried from Q4 2025)
**Status:** 0/20 applications complete (0%)

**Objective:** To package 20 popular open-source applications to run on Hop3, demonstrating the platform's capabilities.

**Requirements for "Complete":**
- Working hop3.toml for each application
- Deployed and tested in production
- Experience report documenting challenges and solutions
- E2E tests passing

**Deliverables:**

### M4.1 - First 5 Applications
**Status:** ⚠️ IN PROGRESS

| App | hop3.toml | Deployed | Tested in Prod | Experience Report |
|-----|-----------|----------|----------------|-------------------|
| 1. WordPress | ⏳ | ❌ | ❌ | ❌ |
| 2. NextCloud | ⏳ | ❌ | ❌ | ❌ |
| 3. Ghost | ⏳ | ❌ | ❌ | ❌ |
| 4. HedgeDoc | ⏳ | ❌ | ❌ | ❌ |
| 5. Gitea | ⏳ | ❌ | ❌ | ❌ |

### M4.2 - Next 5 Applications
**Status:** ⏳ NOT STARTED

| App | hop3.toml | Deployed | Tested in Prod | Experience Report |
|-----|-----------|----------|----------------|-------------------|
| 6. Discourse | ❌ | ❌ | ❌ | ❌ |
| 7. Mastodon | ❌ | ❌ | ❌ | ❌ |
| 8. Matrix/Synapse | ❌ | ❌ | ❌ | ❌ |
| 9. Plausible | ❌ | ❌ | ❌ | ❌ |
| 10. Umami | ❌ | ❌ | ❌ | ❌ |

### M4.3 - Next 5 Applications
**Status:** ⏳ NOT STARTED

| App | hop3.toml | Deployed | Tested in Prod | Experience Report |
|-----|-----------|----------|----------------|-------------------|
| 11. Mattermost | ❌ | ❌ | ❌ | ❌ |
| 12. Rocket.Chat | ❌ | ❌ | ❌ | ❌ |
| 13. BookStack | ❌ | ❌ | ❌ | ❌ |
| 14. Wiki.js | ❌ | ❌ | ❌ | ❌ |
| 15. Etherpad | ❌ | ❌ | ❌ | ❌ |

### M4.4 - Last 5 Applications
**Status:** ⏳ NOT STARTED

| App | hop3.toml | Deployed | Tested in Prod | Experience Report |
|-----|-----------|----------|----------------|-------------------|
| 16. Kanboard | ❌ | ❌ | ❌ | ❌ |
| 17. Wekan | ❌ | ❌ | ❌ | ❌ |
| 18. Invoice Ninja | ❌ | ❌ | ❌ | ❌ |
| 19. Monica CRM | ❌ | ❌ | ❌ | ❌ |
| 20. Cal.com | ❌ | ❌ | ❌ | ❌ |

**Note:** Application list may be adjusted based on complexity and dependencies. See `local-notes/PLAN-2026-Q1.md` for detailed schedule.

## T5: Dissemination & Engagement

**Target:** Q1 2026 (carried from Q4 2025)
**Status:** 3/5 complete (60%)

**Objective:** To promote the Hop3 open-source platform to ensure its adoption and build a community around it.

**Deliverables:**

* **M5.1 Website, blog:** ⚠️ **IN PROGRESS**
  - [x] Basic website exists (hop3.cloud)
  - [x] Blog with release announcements and conference talks (2026-02-17)
    - Release 0.4 announcement
    - OW2Con 2025 (video + slides)
    - OSXP 2025 (video + slides)
  - [ ] Enriched website with feature showcase
  - [ ] Application showcase gallery
  - [ ] Production deployment of new site

* **M5.2 Documentation:** ✅ **COMPLETED** (2026-02-17)
  - [x] New documentation site with Zensical (`zdocs/`)
  - [x] 7-tab navigation: Home, Get Started, Guides, Tutorials, Developers, Blog, Reference
  - [x] 33 end-user tutorials across 9 languages (Python, JS, Go, Ruby, Rust, Java, PHP, Elixir, .NET)
  - [x] Developer documentation (architecture, testing, plugins, packages)
  - [x] CLI cheat sheet and testing cheat sheet
  - [x] Installation guide, quickstart guide
  - [x] hop3.toml configuration reference
  - [x] Index pages for all major sections
  - [x] Tutorial conversion pipeline (test syntax → standard markdown)
  - [ ] Deploy to hop3.cloud (pending)

* **M5.3 Technical report and/or research paper:** ⚠️ **IN PROGRESS**
  - [x] Draft technical report (TR-01, 2026-02-17)
    - Architecture overview
    - Security features documentation
    - Project status summary
  - [ ] Internal review
  - [ ] Final publication

* **M5.4 Conference presentation or workshop:** ✅ **COMPLETED** (2025-12-16)
  - [x] Presented at OW2Con in Paris (Junue 2025)
  - [x] Presented at OSXP in Paris (December 2025)
  - [ ] Additional conference proposals planned for 2026

* **M5.6 Videos/screencasts:** ⏳ **NOT STARTED**
  - [ ] Getting started screencast
  - [ ] Deployment tutorial video
  - [ ] Feature showcase videos (3-5 videos)
  - [ ] Production deployment demo
