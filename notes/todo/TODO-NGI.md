# TODO for the NGI Project

Detailed breakdown of the work items and deliverables, based on the MOU for the "Nix Integration for Hop3" project.

## Timeline Summary

| Task | Target | Status |
|------|--------|--------|
| **T1: Nix Build Plugins** | Q1 2026 | Not Started |
| **T2: Nix Runtime** | Q1 2026 | Not Started |
| **T3: Security & Resilience** | **Q4 2025** | 6/8 Complete (75%) |
| **T4: Packaged Applications** | **Q4 2025** | 0/20 Complete (0%) |
| **T5: Dissemination & Engagement** | **Q4 2025** | 2/5 Complete (40%) |

**Note (2025-12-16):** All non-Nix items (T3, T4, T5) must be completed and **tested in production** by end of Q4 2025. Nix-related work (T1, T2) deferred to Q1 2026.

## TOC

<!-- toc -->

- [T1: Nix Build Plugins for Hop3](#t1-nix-build-plugins-for-hop3)
- [T2: Nix Runtime](#t2-nix-runtime)
- [T3: Security & Resilience](#t3-security--resilience)
- [T4: Packaged Applications](#t4-packaged-applications)
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

**Target:** Q4 2025 (MUST COMPLETE)
**Status:** 6/8 milestones complete (75%)

**Objective:** To improve the security and resilience of Hop3 by adding robust features and tools.

**Deliverables:**
* **M3.1 Backing services:** ✅ **COMPLETED** (2025-11-12)
  - [x] PostgreSQL service plugin with encrypted credentials (Fernet AEAD)
  - [x] Redis service plugin with connection management
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

* **M3.4 Testing framework and infrastructure:** ✅ **COMPLETED** (2025-11-24)
  - [x] 435 tests across 4 layers (232 unit, 128 integration, 14 system, 21 E2E, 40 dashboard)
  - [x] 98.5% integration test pass rate (2 skipped due to test client limitations)
  - [x] 100% pass rate for all other test types
  - [x] CI automation with GitHub Actions
  - [x] Docker-based E2E test infrastructure
  - [x] Pluggy+Dishka DI testing patterns

* **M3.5 Firewalls:** ⚠️ **IN PROGRESS** - MUST COMPLETE Q4 2025
  - [ ] Network-level firewalls configuration
  - [ ] Web Application Firewall (WAF) integration
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
  - [x] 40/40 dashboard view tests passing (100%)
  - [x] Guard-based authentication

* **M3.8 Process outcomes of security audit:** ⚠️ **IN PROGRESS** - MUST COMPLETE Q4 2025
  - [x] JWT token revocation implemented (2025-11-13)
  - [x] Token tampering protection
  - [x] SQL injection prevention
  - [x] Hardcoded password removal
  - [ ] Formal security audit
  - [ ] Accessibility scan
  - [ ] Production verification of all security measures

## T4: Packaged Applications

**Target:** Q4 2025 (MUST COMPLETE)
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

**Note:** Application list may be adjusted based on complexity and dependencies. See `local-notes/DEMO-PORTING-PLAN.md` for porting strategy.

## T5: Dissemination & Engagement

**Target:** Q4 2025 (MUST COMPLETE)
**Status:** 2/5 complete (40%)

**Objective:** To promote the Hop3 open-source platform to ensure its adoption and build a community around it.

**Deliverables:**

* **M5.1 Website, blog:** ⚠️ **IN PROGRESS**
  - [x] Basic website exists (hop3.cloud)
  - [ ] Enriched website with feature showcase
  - [ ] Regular blog posts (at least 2-3 posts)
  - [ ] Application showcase gallery
  - [ ] Production deployment verified

* **M5.2 Documentation:** ⚠️ **IN PROGRESS**
  - [x] Basic developer documentation (docs/src/dev/)
  - [x] Installation guide
  - [x] Quickstart guide
  - [ ] Administrator manual (complete)
  - [ ] End-user tutorials
  - [ ] hop3.toml reference (complete with all sections)
  - [ ] Troubleshooting guide
  - [ ] Production verification

* **M5.3 Technical report and/or research paper:** ⏳ **NOT STARTED**
  - [ ] Draft technical report
  - [ ] Peer review
  - [ ] Final publication
  - Target: Submit by end of Q4 2025

* **M5.4 Conference presentation or workshop:** ✅ **COMPLETED** (2025-12-16)
  - [x] Presented at demo event (December 2025)
  - [x] Additional conference proposals planned for 2026

* **M5.6 Videos/screencasts:** ⏳ **NOT STARTED**
  - [ ] Getting started screencast
  - [ ] Deployment tutorial video
  - [ ] Feature showcase videos (3-5 videos)
  - [ ] Production deployment demo
  - Target: Complete by end of Q4 2025
