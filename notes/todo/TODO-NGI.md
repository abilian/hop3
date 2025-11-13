# TODO for the NGI Project

Detailed breakdown of the work items and deliverables, based on the MOU for the "Nix Integration for Hop3" project, :

 ### T1: Nix Build Plugins for Hop3

 **Objective:** This task focuses on enhancing Hop3 by integrating the Nix package manager to create reproducible build environments and improve flexibility.

 **Deliverables:**
 * **M1.1 Nix "native" builder:** A builder for applications that already have a Nix expression, integrating them into Hop3's workflow.
 * **M1.2 Nix alternatives to existing builders:** Nix-based alternatives for builders such as Python, Nodejs, Ruby, Go, Rust, and Java, following a "12 Factor App" like workflow.

 ### T2: Nix Runtime

 **Objective:** To extend Hop3 by using Nix to create and manage application runtime environments, ensuring consistency and reproducibility.

 **Deliverables:**
 * **M2.1 Specifications and Proof of Concept:** Initial design and feasibility demonstration of the Nix-based runtime.
 * **M2.2 Bêta implementation:** A functional beta version of the Nix runtime integration.
 * **M2.3 Final release ("1.0"):** The stable, production-ready version of the Nix runtime.

 ### T3: Security & Resilience

 **Objective:** To improve the security and resilience of Hop3 by adding robust features and tools.

 **Deliverables:**
 * **M3.1 Backing services:** ✅ **COMPLETED** (2025-11-12) - PostgreSQL service plugin with encrypted credentials (Fernet AEAD)
 * **M3.2 Upgrades:** Mechanisms for seamless platform and application updates, including data migrations.
 * **M3.3 Backups:** ✅ **COMPLETED** (2025-11-13) - Full backup/restore system with service data, checksums, and fail-fast behavior (46 tests)
 * **M3.4 Testing framework and infrastructure:** ✅ **COMPLETED** (2025-11-08) - 329 tests across 4 layers (unit, integration, system, E2E) with CI automation
 * **M3.5 Firewalls:** Network-level firewalls and a Web Application Firewall (WAF).
 * **M3.6 CLI (basic):** ✅ **COMPLETED** (2025-11-08) - Rich CLI with color formatting, confirmation prompts, and message type conventions (30 CLI tests)
 * **M3.7 Web UI (basic):** ✅ **COMPLETED** (2025-11-13) - Production-ready dashboard with SSE log streaming, service management, and backup UI (128 integration tests)
 * **M3.8 Process outcomes of security audit and accessibility scan:** The results and implemented improvements from security and accessibility assessments.

 ### T4: Packaged Applications

 **Objective:** To package 20 popular open-source applications to run on Hop3, demonstrating the platform's capabilities.

 **Deliverables:**
 * **M4.1 - 5 first applications + experience reports:** The initial set of packaged applications along with reports on the process.
 * **M4.2 - 5 next applications + experience reports:** The second set of packaged applications and corresponding reports.
 * **M4.3 - 5 next applications + experience reports:** The third set of packaged applications and their reports.
 * **M4.4 - 5 last applications + experience reports:** The final set of packaged applications and experience reports.

 ### T5: Dissemination & Engagement

 **Objective:** To promote the Hop3 open-source platform to ensure its adoption and build a community around it.

 **Deliverables:**
 * **M5.1 Website, blog:** An enriched website and blog with regular updates.
 * **M5.2 Documentation:** Comprehensive documentation for developers, administrators, and end-users.
 * **M5.3 Technical report and/or research paper:** A paper highlighting the project's outcomes.
 * **M5.4 Conference presentation or workshop:** Presentation of the project at industry events.
 * **M5.6 Videos/screencasts:** Instructional videos and screencasts about Hop3.
