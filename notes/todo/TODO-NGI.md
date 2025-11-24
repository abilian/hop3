# TODO for the NGI Project

Detailed breakdown of the work items and deliverables, based on the MOU for the "Nix Integration for Hop3" project, :

## TOC

<!-- toc -->

- [T1: Nix Build Plugins for Hop3](#t1-nix-build-plugins-for-hop3)
- [T2: Nix Runtime](#t2-nix-runtime)
- [T3: Security & Resilience](#t3-security--resilience)
- [T4: Packaged Applications](#t4-packaged-applications)
- [T5: Dissemination & Engagement](#t5-dissemination--engagement)

<!-- tocstop -->

## T1: Nix Build Plugins for Hop3

**Objective:** This task focuses on enhancing Hop3 by integrating the Nix package manager to create reproducible build environments and improve flexibility.

**Deliverables:**
* **M1.1 Nix "native" builder:** A builder for applications that already have a Nix expression, integrating them into Hop3's workflow.
* **M1.2 Nix alternatives to existing builders:** Nix-based alternatives for builders such as Python, Nodejs, Ruby, Go, Rust, and Java, following a "12 Factor App" like workflow.

## T2: Nix Runtime

**Objective:** To extend Hop3 by using Nix to create and manage application runtime environments, ensuring consistency and reproducibility.

**Deliverables:**
* **M2.1 Specifications and Proof of Concept:** Initial design and feasibility demonstration of the Nix-based runtime.
* **M2.2 Bêta implementation:** A functional beta version of the Nix runtime integration.
* **M2.3 Final release ("1.0"):** The stable, production-ready version of the Nix runtime.

## T3: Security & Resilience

**Objective:** To improve the security and resilience of Hop3 by adding robust features and tools.

**Overall Status:** 6/8 milestones complete (75%)

**Deliverables:**
* **M3.1 Backing services:** ✅ **COMPLETED** (2025-11-12)
  - PostgreSQL service plugin with encrypted credentials (Fernet AEAD)
  - Redis service plugin with connection management
  - Service credential persistence in database
  - Backup/restore integration for services

* **M3.2 Upgrades:** ✅ **COMPLETED** (2025-11-13)
  - Alembic database migration system implemented
  - Automatic migrations on server startup
  - Rollback capability for schema changes
  - Safe production upgrades enabled

* **M3.3 Backups:** ✅ **COMPLETED** (2025-11-13)
  - Full backup/restore system with service data
  - SHA256 checksums for verification
  - Fail-fast behavior (backup fails if services cannot be backed up)
  - 46 tests (18 unit + 9 E2E + 19 integration)

* **M3.4 Testing framework and infrastructure:** ✅ **COMPLETED** (2025-11-24)
  - 435 tests across 4 layers (232 unit, 128 integration, 14 system, 21 E2E, 40 dashboard)
  - 98.5% integration test pass rate (2 skipped due to test client limitations)
  - 100% pass rate for all other test types
  - CI automation with GitHub Actions
  - Docker-based E2E test infrastructure
  - Pluggy+Dishka DI testing patterns

* **M3.5 Firewalls:** ❌ **NOT STARTED**
  - Network-level firewalls configuration
  - Web Application Firewall (WAF) integration
  - *Priority: Phase 3 (Q2 2026)*

* **M3.6 CLI (basic):** ✅ **COMPLETED** (2025-11-08)
  - Rich CLI with color formatting
  - Confirmation prompts for destructive operations
  - Message type conventions (info, warning, error, success)
  - 30 CLI tests passing

* **M3.7 Web UI (basic):** ✅ **COMPLETED** (2025-11-24)
  - Production-ready dashboard with Litestar
  - Server-Sent Events (SSE) log streaming
  - Service management pages
  - Backup UI (list, restore, delete)
  - 40/40 dashboard view tests passing (100%)
  - Guard-based authentication

* **M3.8 Process outcomes of security audit:** ⚠️ **PARTIALLY COMPLETE**
  - JWT token revocation implemented (2025-11-13)
  - Token tampering protection
  - SQL injection prevention
  - Hardcoded password removal
  - *Remaining:* Formal security audit + accessibility scan
  - *Priority: Phase 3 (Q1 2026)*

## T4: Packaged Applications

**Objective:** To package 20 popular open-source applications to run on Hop3, demonstrating the platform's capabilities.

**Deliverables:**
* **M4.1 - 5 first applications + experience reports:** The initial set of packaged applications along with reports on the process.
* **M4.2 - 5 next applications + experience reports:** The second set of packaged applications and corresponding reports.
* **M4.3 - 5 next applications + experience reports:** The third set of packaged applications and their reports.
* **M4.4 - 5 last applications + experience reports:** The final set of packaged applications and experience reports.

## T5: Dissemination & Engagement

**Objective:** To promote the Hop3 open-source platform to ensure its adoption and build a community around it.

**Deliverables:**
* **M5.1 Website, blog:** An enriched website and blog with regular updates.
* **M5.2 Documentation:** Comprehensive documentation for developers, administrators, and end-users.
* **M5.3 Technical report and/or research paper:** A paper highlighting the project's outcomes.
* **M5.4 Conference presentation or workshop:** Presentation of the project at industry events.
* **M5.6 Videos/screencasts:** Instructional videos and screencasts about Hop3.
