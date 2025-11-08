# CRA Conformity Assessment - Hop3

**Document Version:** 1.0
**Date:** 2025-11-08
**Status:** IN_PROGRESS
**Prepared By:** Abilian SAS / Hop3 Development Team
**Contact:** [compliance@abilian.com](mailto:compliance@abilian.com)

---

## 1️⃣ **Project Identification**

### **Product Name**
Hop3 (Hop³ / Hop cubed)

### **Product Description**
Hop3 is an open-source Platform as a Service (PaaS) that enables users to deploy and manage web applications seamlessly on their own infrastructure. It is designed to enhance cloud computing with a focus on sovereignty, security, sustainability, and inclusivity. Hop3 provides a lightweight alternative to containerization platforms like Docker and Kubernetes, targeting SMEs, non-profits, public services, and individual developers.

### **Product Version**
- **Stable Release:** v0.3.0
- **Development Version:** v0.4.0 (in active development)

### **Manufacturer**
**Organization:** Abilian SAS
**Address:** Paris, France
**Contact Email:** [contact@abilian.com](mailto:contact@abilian.com)
**Website:** [https://abilian.com](https://abilian.com)
**Project Website:** [https://hop3.cloud](https://hop3.cloud)

### **Repositories**
- **Primary:** [https://github.com/abilian/hop3](https://github.com/abilian/hop3)
- **Mirror:** [https://git.sr.ht/~sfermigier/hop3](https://git.sr.ht/~sfermigier/hop3)
- **Research:** [https://gitlab.eclipse.org/eclipse-research-labs/nephele-project/opencall-2/h3ni/hop3-h3ni](https://gitlab.eclipse.org/eclipse-research-labs/nephele-project/opencall-2/h3ni/hop3-h3ni)

### **License**
AGPL-3.0-only (except for vendored code)

### **Classification**

| **Category**          | **Level**            | **Justification** |
|-----------------------|----------------------|-------------------|
| **Confidentiality**   | [MODERATE] | Hop3 manages application configurations, environment variables, and deployment settings which may contain sensitive information (API keys, database credentials). Multi-tenant scenarios require isolation. |
| **Integrity**         | [CRITICAL] | As a PaaS platform, Hop3 controls application deployment, orchestration, and infrastructure. Compromise of integrity could lead to unauthorized code execution, data corruption, or service disruption. |
| **Availability**      | [HIGH] | Hop3 manages production applications and services. Downtime affects hosted applications and their end users. Automated backups and restore capabilities are essential. |
| **RTO** (Recovery Time) | **< 4 hours** | Target recovery time for platform services to minimize impact on hosted applications. |
| **RPO** (Recovery Point) | **< 1 hour** | Maximum acceptable data loss window for application configurations and state. |

---

## 2️⃣ **CRA Scope & Classification**

### **CRA Applicability**

| **Criteria**                     | **Assessment** | **Notes** |
|----------------------------------|----------------|-----------|
| **Product with digital elements?** | [YES] | Hop3 is software infrastructure for deploying and managing web applications. |
| **Placed on EU market?**         | [YES] | Open-source project available globally, including EU. |
| **Free and open-source software?** | [YES] | Licensed under AGPL-3.0, hosted on public repositories. |
| **Commercial activity?**         | [PARTIAL] | Developed by Abilian SAS, which may offer commercial support services. Core project is non-commercial OSS. |

### **CRA Classification**

**Classification:** [STANDARD] (Self-Assessment Required)

**Rationale:**
- Hop3 is primarily a non-commercial open-source project (AGPL-3.0)
- Does not fall under Annex III (critical products requiring third-party assessment)
- Not a Class I or Class II product under CRA definitions
- Self-assessment approach is appropriate under Article 24 (for free and open-source software)
- While commercial support may be offered by Abilian SAS, the core platform is developed and distributed as OSS

**Article 24 Considerations (FOSS Exception):**
- [DONE] Source code is publicly available
- [DONE] Developed in an open, transparent manner
- [DONE] Not intended for integration into commercial products (standalone PaaS)
- [WARNING] Commercial support available from Abilian SAS (requires transparency)

**Recommendation:** Continue as non-commercial OSS with self-assessment. If commercial offerings expand significantly, re-evaluate classification.

---

## 3️⃣ **Technical Documentation**

### **Architecture Overview**

Hop3 uses a modular, plugin-based architecture:

- **Core Server** (`hop3-server`): Deployment engine, web UI, application lifecycle management
- **CLI Tool** (`hop3-cli`): Command-line interface for remote management via JSON-RPC
- **Testing Framework** (`hop3-testing`): E2E and integration test infrastructure
- **Plugin System**: Pluggy-based extensibility for proxies (Nginx, Caddy, Traefik), operating systems (Debian, RHEL, Arch, BSD, macOS), and services

**Key Technologies:**
- Python 3.10+
- SQLAlchemy (database ORM)
- Starlette (web framework)
- Nix (reproducible builds and package management)
- POSIX isolation (lightweight alternatives to containers)

### **System Architecture Diagram**

```
┌─────────────────────────────────────────────────────────┐
│                    Hop3 Web UI                          │
│            (Starlette + HTMX/Alpine.js)                 │
└─────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│                 Hop3 Core Server                        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │ Deployment   │  │ Orchestration│  │ User/Access  │  │
│  │ Engine       │  │ Engine       │  │ Control      │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │ App Lifecycle│  │ Domain/SSL   │  │ Backup/      │  │
│  │ Manager      │  │ Manager      │  │ Restore      │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
└─────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│              Plugin Layer (Pluggy-based)                │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │ Proxy Plugins│  │ OS Plugins   │  │ Service      │  │
│  │ (Nginx,      │  │ (Debian,     │  │ Plugins      │  │
│  │  Caddy,      │  │  RHEL, BSD,  │  │              │  │
│  │  Traefik)    │  │  Arch, macOS)│  │              │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
└─────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│          Infrastructure & Applications                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │ Deployed     │  │ Reverse      │  │ SSL/TLS      │  │
│  │ Applications │  │ Proxy        │  │ (Let's       │  │
│  │              │  │              │  │  Encrypt)    │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
└─────────────────────────────────────────────────────────┘
```

### **Security Architecture**

- **Authentication & Authorization:** LDAP integration, SSO support, Role-Based Access Control (RBAC)
- **Network Security:** Integrated firewall management, VPN support, secure proxy configurations
- **Data Protection:** Encryption in transit (TLS), automated SSL certificate management (Let's Encrypt)
- **Isolation:** POSIX-based process isolation, user/group separation
- **Monitoring:** Real-time monitoring, audit logging, alert capabilities

### **Technical Documentation Location**

| **Document**              | **Location** | **Status** |
|---------------------------|--------------|------------|
| Architecture Overview     | `docs/src/dev/architecture.md` | [DONE] |
| Installation Guide        | `docs/src/installation.md` | [DONE] |
| Features Documentation    | `docs/src/features.md` | [DONE] |
| Testing Strategy          | `docs/src/dev/testing-strategy.md` | [DONE] |
| Orchestration Details     | `docs/src/dev/orchestration.md` | [DONE] |
| API Reference             | TBD | GAP-01 |
| Security Hardening Guide  | TBD | GAP-02 |
| Threat Model              | TBD | GAP-03 |

---

## 4️⃣ **Risk Assessment**

### **Threat Model Summary**

**Primary Attack Vectors:**
1. **Unauthorized Access to Web UI:** Compromise of admin credentials could allow attacker to deploy malicious applications or modify configurations.
2. **Application Isolation Bypass:** Weak process isolation could allow one deployed application to access another's data or resources.
3. **Supply Chain Attacks:** Malicious dependencies in application deployments or in Hop3's own dependency tree.
4. **Privilege Escalation:** Exploitation of deployment mechanisms to gain elevated system access.
5. **Data Exfiltration:** Access to environment variables, database credentials, or application data.
6. **Denial of Service:** Resource exhaustion attacks targeting the orchestration engine or deployed applications.

### **Risk Assessment Matrix**

| **Threat**                          | **Likelihood** | **Impact** | **Risk Level** | **Mitigation** |
|-------------------------------------|----------------|------------|----------------|----------------|
| Unauthorized Web UI Access          | Medium         | Critical   | HIGH        | LDAP/SSO, RBAC, audit logging, 2FA (planned) |
| Application Isolation Bypass        | Low            | Critical   | MEDIUM      | POSIX isolation, user/group separation, sandboxing (planned) |
| Supply Chain Attack (Hop3)          | Medium         | Critical   | HIGH        | Nix reproducible builds, SBOM generation, dependency scanning |
| Supply Chain Attack (Deployed Apps) | High           | High       | HIGH        | User responsibility; provide guidance on secure practices |
| Privilege Escalation                | Low            | Critical   | MEDIUM      | Least privilege principle, restricted file permissions |
| Data Exfiltration (Env Vars)        | Medium         | High       | MEDIUM      | Encrypted storage (planned), access controls, audit logs |
| Denial of Service                   | Medium         | Medium     | LOW-MEDIUM  | Rate limiting (planned), resource quotas, monitoring |
| SSL/TLS Certificate Compromise      | Low            | High       | LOW-MEDIUM  | Automated cert rotation, Let's Encrypt integration |

### **STRIDE Analysis**

| **STRIDE Category** | **Threats Identified** | **Mitigations** |
|---------------------|------------------------|-----------------|
| **Spoofing**        | Impersonation of legitimate users, API credential theft | LDAP/SSO integration, RBAC, audit logging |
| **Tampering**       | Modification of application code, configuration tampering | Git-based deployments with integrity checks, file permissions |
| **Repudiation**     | Denial of deployment or configuration changes | Comprehensive audit logging, immutable logs (planned) |
| **Information Disclosure** | Exposure of environment variables, database credentials | Access controls, encrypted storage (planned) |
| **Denial of Service** | Resource exhaustion, orchestration disruption | Resource quotas (planned), monitoring, rate limiting (planned) |
| **Elevation of Privilege** | Gaining admin access, container escape (N/A) | Least privilege, RBAC, secure deployment process |

### **Residual Risks**

1. **User-Deployed Application Security:** Hop3 cannot guarantee security of applications deployed by users. **Mitigation:** Provide security best practices documentation.
2. **Third-Party Dependency Vulnerabilities:** Hop3 relies on system packages and Python dependencies. **Mitigation:** Automated vulnerability scanning, timely updates.
3. **Early Development Stage:** v0.3.0 is first usable version; v0.4.0 is undergoing major refactoring. **Mitigation:** Clear warnings about production readiness, extensive testing before stable releases.

**Full Threat Model Document:** GAP-03 (Target: 2025-12-31)

---

## 5️⃣ **Essential Cybersecurity Requirements (CRA Annex I)**

### **Section 1: Security by Design and by Default**

| **Requirement** | **Status** | **Implementation** | **Evidence** |
|-----------------|------------|-------------------|--------------|
| **1.1 Secure Development Process** | [PARTIAL] | - REUSE compliance for licensing<br>- Four-layer testing pyramid (unit, integration, system, E2E)<br>- CI/CD on SourceHut (multiple OS/distros)<br>- Code quality: Ruff, Pyrefly, pre-commit hooks<br>Missing: Formal SDLC documentation, security training | - `LICENSES/` directory<br>- `docs/src/dev/testing-strategy.md`<br>- `.builds/` CI scripts<br>- `pyproject.toml` (Ruff config)<br>**GAP-04:** SDLC documentation (Target: 2025-10-31) |
| **1.2 Secure by Default Configuration** | [PARTIAL] | - RBAC with granular permissions<br>- LDAP/SSO integration for authentication<br>- Automated SSL/TLS with Let's Encrypt<br>Missing: Default deny firewall rules, 2FA enforcement, secure defaults documentation | - `docs/src/features.md` (RBAC, SSO)<br>- Proxy plugin SSL automation<br>**GAP-02:** Security hardening guide (Target: 2025-11-30) |
| **1.3 Protection Against Unauthorized Access** | [PARTIAL] | - RBAC implementation<br>- Audit logging for user actions<br>- File permission controls<br>Missing: 2FA, session timeout enforcement | - `packages/hop3-server/src/hop3/orm/` (RBAC models)<br>**GAP-05:** 2FA implementation (Target: 2026-01-31) |
| **1.4 Input Validation** | [PARTIAL] | - SQLAlchemy ORM prevents SQL injection<br>- Starlette framework request validation<br>Missing: Comprehensive input validation layer, fuzzing tests | - Database abstractions via Advanced Alchemy<br>**GAP-06:** Input validation audit (Target: 2025-12-15) |
| **1.5 Data Protection** | [PARTIAL] | - TLS for data in transit<br>- Automated certificate management<br>Missing: Encryption at rest for env vars, secret management | - Let's Encrypt integration<br>**GAP-07:** Secret management system (Target: 2026-02-28) |

### **Section 2: Vulnerability Handling**

| **Requirement** | **Status** | **Implementation** | **Evidence** |
|-----------------|------------|-------------------|--------------|
| **2.1 Vulnerability Disclosure Policy** | [PLANNED] | No formal VDP published | **GAP-08:** Publish VDP at `SECURITY.md` (Target: 2025-10-15) |
| **2.2 Coordinated Vulnerability Disclosure** | [PLANNED] | No CVD process established | **GAP-09:** Establish CVD process, security contact (Target: 2025-10-15) |
| **2.3 Timely Security Updates** | [PARTIAL] | - Dependency updates via `uv` and Poetry<br>- CI tests on multiple OS/distros<br>Missing: Automated vulnerability scanning, SLA for patches | - `pyproject.toml` dependency specs<br>- `.builds/` CI infrastructure<br>**GAP-10:** Dependabot/Renovate setup (Target: 2025-10-31) |
| **2.4 Public Vulnerability Database** | [PLANNED] | No integration with CVE/OSV databases | **GAP-11:** CVE numbering authority registration (Target: 2026-01-31) |

### **Section 3: Software Bill of Materials (SBOM)**

| **Requirement** | **Status** | **Implementation** | **Evidence** |
|-----------------|------------|-------------------|--------------|
| **3.1 SBOM Generation** | [PARTIAL] | - Nix-based reproducible builds provide transparent dependency tree<br>Missing: Automated SBOM generation in CI/CD | - `shell.nix`, Nix integration<br>- `pyproject.toml` dependencies<br>**GAP-12:** CycloneDX SBOM generation (Target: 2025-11-30) |
| **3.2 SBOM Format** | [PLANNED] | No standardized SBOM output (SPDX/CycloneDX) | **GAP-12:** Use CycloneDX format (Target: 2025-11-30) |
| **3.3 SBOM Publication** | [PLANNED] | SBOM not included in releases | **GAP-13:** Publish SBOM with GitHub releases (Target: 2025-12-15) |

### **Section 4: Incident Response**

| **Requirement** | **Status** | **Implementation** | **Evidence** |
|-----------------|------------|-------------------|--------------|
| **4.1 Incident Response Plan** | [PLANNED] | No formal incident response plan | **GAP-14:** Incident response plan (Target: 2026-01-15) |
| **4.2 Monitoring and Alerting** | [PARTIAL] | - Real-time monitoring dashboard (web UI)<br>- Event logs and audit trails<br>Missing: Automated alerting, SIEM integration | - `docs/src/features.md` (monitoring)<br>**GAP-15:** Alerting system (Target: 2026-02-28) |
| **4.3 Forensics and Root Cause Analysis** | [PARTIAL] | - Comprehensive audit logging<br>Missing: Log retention policy, forensic procedures | - Audit log implementation<br>**GAP-16:** Log retention policy (Target: 2025-12-31) |

### **Section 5: Supply Chain Security**

| **Requirement** | **Status** | **Implementation** | **Evidence** |
|-----------------|------------|-------------------|--------------|
| **5.1 Dependency Management** | [DONE] | - `uv` for Python package management<br>- Nix for reproducible builds<br>- Poetry for dependency resolution<br>- Workspace-based monorepo structure | - `pyproject.toml` (workspace config)<br>- `shell.nix`<br>- `uv.lock` files |
| **5.2 Dependency Vulnerability Scanning** | [PLANNED] | No automated scanning in CI/CD | **GAP-10:** Dependabot/Renovate + FOSSA (Target: 2025-10-31) |
| **5.3 Build Reproducibility** | [DONE] | - Nix-based hermetic builds<br>- Lockfiles for all dependencies | - `shell.nix`<br>- Nix integration for deterministic builds |
| **5.4 Supply Chain Attestations** | [PLANNED] | No SLSA attestations or provenance | **GAP-17:** SLSA Level 2 provenance (Target: 2026-02-28) |

---

## 6️⃣ **Conformity Assessment Evidence**

### **Security Posture Metrics**

| **Metric**                | **Status** | **Target** | **Evidence** |
|---------------------------|------------|------------|--------------|
| **OpenSSF Scorecard**     | [NOT ENABLED] | 7.0+ | **GAP-18:** Enable OpenSSF Scorecard (Target: 2025-11-15) |
| **CII Best Practices**    | [NOT REGISTERED] | Passing | **GAP-19:** Register for CII badge (Target: 2025-12-01) |
| **FOSSA License Compliance** | [NOT ENABLED] | 100% | **GAP-20:** FOSSA integration (Target: 2025-11-30) |
| **SonarCloud Quality Gate** | [NOT ENABLED] | A Rating | **GAP-21:** SonarCloud onboarding (Target: 2025-11-15) |
| **Test Coverage**         | [PARTIAL] | 80%+ | Current coverage TBD; E2E framework complete |

### **Compliance Artifacts**

| **Artifact**              | **Status** | **Location** |
|---------------------------|------------|--------------|
| **REUSE Compliance**      | [COMPLETE] | `LICENSES/`, all files have headers |
| **License File**          | [COMPLETE] | `LICENSE` (AGPL-3.0) |
| **Code of Conduct**       | [COMPLETE] | `docs/policies/code-of-conduct.md` |
| **Contributing Guide**    | [COMPLETE] | `docs/dev/contributing.md` |
| **Security Policy**       | [MISSING] | **GAP-08:** `SECURITY.md` (Target: 2025-10-15) |
| **SBOM**                  | [MISSING] | **GAP-12:** Generate with releases (Target: 2025-11-30) |
| **Threat Model**          | [MISSING] | **GAP-03:** Full threat model (Target: 2025-12-31) |
| **Incident Response Plan** | [MISSING] | **GAP-14:** IRP document (Target: 2026-01-15) |

### **Release Attestations**

| **Release** | **Attestation** | **SBOM** | **Signatures** |
|-------------|-----------------|----------|----------------|
| v0.3.0      | No          | No    | No         |
| v0.4.0      | Planned     | Planned | Planned   |

**Target:** All releases from v0.4.0 onwards will include SLSA provenance, SBOM, and GPG signatures.

### **Testing Evidence**

| **Test Layer** | **Status** | **Coverage** | **Location** |
|----------------|------------|--------------|--------------|
| Unit Tests     | [DONE] | TBD | `packages/hop3-server/tests/a_unit/` |
| Integration Tests | [DONE] | TBD | `packages/hop3-server/tests/b_integration/` |
| System Tests   | [DONE] | TBD | `packages/hop3-server/tests/c_system/` |
| E2E Tests      | [DONE] | TBD | `packages/hop3-server/tests/d_e2e/` |

**CI/CD:** Tests run on SourceHut across multiple OS distributions (Ubuntu, Debian, Arch, Rocky, Alma, Fedora, BSD planned).

---

## 7️⃣ **Post-Market Surveillance**

### **Vulnerability Monitoring**

| **Activity**                  | **Status** | **Frequency** | **Responsibility** |
|-------------------------------|------------|---------------|-------------------|
| Dependency vulnerability scanning | [PLANNED] | Daily (automated) | **GAP-10:** CI/CD integration (Target: 2025-10-31) |
| CVE database monitoring       | [PLANNED] | Weekly | Security team (to be established) |
| Security mailing list subscription | [PLANNED] | Continuous | **GAP-22:** Subscribe to relevant lists (Target: 2025-10-31) |
| GitHub Security Advisories    | [PARTIAL] | Continuous | Enabled for repository |

### **User Feedback and Incident Reporting**

| **Channel**               | **Status** | **Location** |
|---------------------------|------------|--------------|
| GitHub Issues             | [ACTIVE]  | [https://github.com/abilian/hop3/issues](https://github.com/abilian/hop3/issues) |
| Matrix Chat               | [ACTIVE]  | [#hop3:matrix.org](https://matrix.to/#/#hop3:matrix.org) |
| Security Email            | [PLANNED] | **GAP-08:** security@abilian.com (Target: 2025-10-15) |
| Community Forums          | [PLANNED] | TBD |

### **Update and Patch Management**

| **Process**               | **Status** | **SLA** | **Notes** |
|---------------------------|------------|---------|-----------|
| Critical security patches | [PLANNED] | < 7 days | **GAP-23:** Establish patch SLA (Target: 2025-11-30) |
| High severity patches     | [PLANNED] | < 14 days | **GAP-23:** Establish patch SLA (Target: 2025-11-30) |
| Dependency updates        | [AD-HOC] | Monthly | Needs formalization |
| Release cadence           | [UNDEFINED] | TBD | **GAP-24:** Define release schedule (Target: 2025-11-30) |

### **Metrics and KPIs**

| **Metric**                | **Target** | **Current** | **Tracking** |
|---------------------------|------------|-------------|--------------|
| Mean Time to Patch (MTTP) | < 7 days (critical) | TBD | **GAP-25:** Establish metrics tracking (Target: 2025-12-31) |
| Vulnerability Response Time | < 24 hours (acknowledgment) | TBD | **GAP-25:** Establish metrics tracking (Target: 2025-12-31) |
| Test Coverage             | > 80%      | TBD | **GAP-26:** Coverage reporting in CI (Target: 2025-11-30) |
| User-Reported Security Issues | 0 unresolved > 30 days | TBD | GitHub Issues tracking |

---

## 8️⃣ **EU Declaration of Conformity**

### **Draft Declaration**

> **EU DECLARATION OF CONFORMITY**
>
> **Product:** Hop3 - Open Source Platform as a Service
> **Version:** 0.4.0+
> **Manufacturer:** Abilian SAS, Paris, France
>
> We, Abilian SAS, declare under our sole responsibility that the product identified above is in conformity with the essential cybersecurity requirements of the Cyber Resilience Act (CRA) Regulation (EU) 2024/XXXX, as applicable to free and open-source software under Article 24.
>
> **Applied Standards and Specifications:**
> - ISO/IEC 27001:2022 (Information Security Management) - Planned
> - OWASP ASVS v4.0 (Application Security Verification Standard) - Partial
> - NIST Cybersecurity Framework v1.1 - Planned
> - SLSA Framework (Supply Chain Security) - Planned
>
> **Conformity Assessment Procedure:** Self-assessment (Article 24, Free and Open-Source Software)
>
> **Status:** IN_PROGRESS
> **Target Completion Date:** 2026-03-31
>
> **Signed:**
> [Name], [Title]
> Abilian SAS
> **Date:** [To be signed upon completion]

**Note:** This declaration will be finalized and signed upon completion of all documented gaps and achievement of full CRA conformity.

---

## 9️⃣ **Assessment Completion & Approval**

### **Current Status**

**Overall Status:** IN_PROGRESS

**Completion Percentage:** ~35%

### **Gap Summary**

| **Gap ID** | **Description** | **Priority** | **Target Date** | **Owner** |
|------------|-----------------|--------------|-----------------|-----------|
| **GAP-01** | API Reference Documentation | Medium | 2025-11-30 | Dev Team |
| **GAP-02** | Security Hardening Guide | High | 2025-11-30 | Security Team |
| **GAP-03** | Formal Threat Model Document | High | 2025-12-31 | Security Team |
| **GAP-04** | SDLC Documentation | Medium | 2025-10-31 | Dev Team |
| **GAP-05** | 2FA Implementation | High | 2026-01-31 | Dev Team |
| **GAP-06** | Input Validation Audit | High | 2025-12-15 | Security Team |
| **GAP-07** | Secret Management System | High | 2026-02-28 | Dev Team |
| **GAP-08** | Vulnerability Disclosure Policy (SECURITY.md) | Critical | 2025-10-15 | Security Team |
| **GAP-09** | Coordinated Vulnerability Disclosure Process | Critical | 2025-10-15 | Security Team |
| **GAP-10** | Automated Dependency Scanning (Dependabot/Renovate) | High | 2025-10-31 | DevOps |
| **GAP-11** | CVE Numbering Authority Registration | Medium | 2026-01-31 | Security Team |
| **GAP-12** | SBOM Generation (CycloneDX) | High | 2025-11-30 | DevOps |
| **GAP-13** | SBOM Publication with Releases | High | 2025-12-15 | DevOps |
| **GAP-14** | Incident Response Plan | High | 2026-01-15 | Security Team |
| **GAP-15** | Automated Alerting System | Medium | 2026-02-28 | DevOps |
| **GAP-16** | Log Retention Policy | Medium | 2025-12-31 | Security Team |
| **GAP-17** | SLSA Level 2 Provenance | High | 2026-02-28 | DevOps |
| **GAP-18** | OpenSSF Scorecard Integration | High | 2025-11-15 | DevOps |
| **GAP-19** | CII Best Practices Badge | High | 2025-12-01 | Dev Team |
| **GAP-20** | FOSSA License Compliance | Medium | 2025-11-30 | Legal/DevOps |
| **GAP-21** | SonarCloud Code Quality | High | 2025-11-15 | DevOps |
| **GAP-22** | Security Mailing List Subscriptions | Medium | 2025-10-31 | Security Team |
| **GAP-23** | Patch Management SLA | High | 2025-11-30 | Security Team |
| **GAP-24** | Release Schedule Definition | Medium | 2025-11-30 | Dev Team |
| **GAP-25** | Security Metrics Tracking | Medium | 2025-12-31 | Security Team |
| **GAP-26** | Coverage Reporting in CI | Medium | 2025-11-30 | DevOps |

### **Milestones**

| **Milestone** | **Target Date** | **Dependencies** | **Status** |
|---------------|-----------------|------------------|------------|
| **M1: Critical Security Baseline** | 2025-10-31 | GAP-08, GAP-09, GAP-10, GAP-18, GAP-21 | [NOT STARTED] |
| **M2: Documentation Complete** | 2025-12-31 | GAP-01, GAP-02, GAP-03, GAP-04, GAP-16, GAP-23, GAP-24 | [NOT STARTED] |
| **M3: Supply Chain Security** | 2025-12-31 | GAP-12, GAP-13, GAP-17 | [NOT STARTED] |
| **M4: Security Features Complete** | 2026-02-28 | GAP-05, GAP-06, GAP-07, GAP-14, GAP-15 | [NOT STARTED] |
| **M5: Full CRA Conformity** | 2026-03-31 | All gaps closed | [NOT STARTED] |

### **Approval**

**Assessment Prepared By:**
Stefane Fermigier, Lead Developer / Project Manager
**Date:** 2025-11-08

**Technical Review:**
[Name], [Title]
**Date:** [Pending]

**Security Review:**
[Name], [Title]
**Date:** [Pending]

**Management Approval:**
[Name], [Title]
**Date:** [Pending]

**Final Approval for EU Declaration:**
[Name], CEO/Authorized Representative
**Date:** [Target: 2026-03-31]

---

## Appendix A: ISMS Policy References

**Note:** Abilian/Hop3 does not currently have a published ISMS framework. The following policies are identified as required for full CRA conformity:

| **Policy** | **Status** | **Target Date** |
|------------|------------|-----------------|
| Information Security Policy | [PLANNED] | 2025-12-31 |
| Access Control Policy | [PLANNED] | 2025-11-30 |
| Incident Response Policy | [PLANNED] | 2026-01-15 |
| Business Continuity Policy | [PLANNED] | 2026-02-28 |
| Risk Management Policy | [PLANNED] | 2025-12-31 |
| Secure Development Policy | [PLANNED] | 2025-10-31 |
| Vulnerability Management Policy | [PLANNED] | 2025-10-31 |
| Change Management Policy | [PLANNED] | 2025-11-30 |

**Recommendation:** Establish ISMS-PUBLIC repository similar to [github.com/Hack23/ISMS-PUBLIC](https://github.com/Hack23/ISMS-PUBLIC) for policy publication and transparency.

---

## Appendix B: Compliance Roadmap

### **Phase 1: Critical Foundation (Oct-Dec 2025)**
- GAP-08: Vulnerability Disclosure Policy
- GAP-09: CVD Process
- GAP-10: Automated Dependency Scanning
- GAP-18: OpenSSF Scorecard
- GAP-19: CII Best Practices Badge
- GAP-21: SonarCloud Integration

### **Phase 2: Documentation & Governance (Oct-Dec 2025)**
- GAP-02: Security Hardening Guide
- GAP-03: Threat Model
- GAP-04: SDLC Documentation
- GAP-23: Patch Management SLA
- GAP-24: Release Schedule

### **Phase 3: Supply Chain Security (Nov-Dec 2025)**
- GAP-12: SBOM Generation
- GAP-13: SBOM Publication
- GAP-20: FOSSA Integration
- GAP-26: Coverage Reporting

### **Phase 4: Security Features (Dec 2025 - Feb 2026)**
- GAP-05: 2FA Implementation
- GAP-06: Input Validation Audit
- GAP-07: Secret Management
- GAP-14: Incident Response Plan
- GAP-17: SLSA Provenance

### **Phase 5: Final Conformity (Mar 2026)**
- EU Declaration of Conformity signature
- Public announcement of CRA compliance
- Badge publication

---

## Appendix C: References

- **CRA Regulation (EU) 2024/XXXX:** [Link to official regulation]
- **Hop3 Documentation:** [https://hop3.cloud](https://hop3.cloud)
- **GitHub Repository:** [https://github.com/abilian/hop3](https://github.com/abilian/hop3)
- **OWASP ASVS:** [https://owasp.org/www-project-application-security-verification-standard/](https://owasp.org/www-project-application-security-verification-standard/)
- **SLSA Framework:** [https://slsa.dev](https://slsa.dev)
- **NIST Cybersecurity Framework:** [https://www.nist.gov/cyberframework](https://www.nist.gov/cyberframework)
- **OpenSSF Scorecard:** [https://securityscorecards.dev/](https://securityscorecards.dev/)
- **CII Best Practices:** [https://bestpractices.coreinfrastructure.org/](https://bestpractices.coreinfrastructure.org/)

---

**Document Control:**

| **Version** | **Date** | **Author** | **Changes** |
|-------------|----------|------------|-------------|
| 1.0         | 2025-11-08 | Hop3 Team | Initial CRA assessment document created |

**Next Review Date:** 2025-12-31

---

**End of CRA Conformity Assessment - Hop3**
