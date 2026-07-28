# ADR 013: Software Supply Chain Security and SBOMs

- **Status**: Accepted
- **Type**: Feature
- **Created**: 2024-07-17
- **Related-ADRs**: [006](./006-nix-integration.md), [008](./008-nix-builders-2.md), [010](./010-security-and-resilience.md), [058](./058-build-reproducibility-model.md) (reproducibility model)

## Context and Goals

Supply chain transparency, traceability, and component-level security are prerequisites for platform integrity and reliability. Hop3 implements Software Bill of Materials (SBOMs) to provide a detailed inventory of software components and to anchor the other supply-chain practices described here.

## Decision

Hop3 adopts a proactive stance towards software supply chain security by integrating comprehensive SBOMs and rigorous security practices throughout the development and delivery pipeline. Dependencies are made transparent, verifiable, and secure, and each release carries a compliance-ready CycloneDX SBOM. Any SBOM generator that produces valid CycloneDX output meets the requirement; Genealogos is a candidate tool but not a committed dependency.

## Key Components

### Software Supply Chain Security

1. **Dependency Management**:

   - **Nix Package Management**: Nix provides deterministic builds and dependency management, ensuring that all software dependencies are explicitly defined, reproducible, and isolated.
   - **Dependency Auditing**: Dependencies are audited for known vulnerabilities using automated tools (`pip-audit` via Nox), and security patches are kept up to date.

1. **Secure Development Practices**:

   - **Code Reviews**: Thorough code reviews and security audits are enforced for all changes to the codebase.
   - **Continuous Integration**: Security checks are integrated into the CI pipeline to detect and address vulnerabilities early in the development process.
   - **REUSE-compliant licensing**: Every source file carries a REUSE-compliant license header, enforced in CI.

1. **Software Bill of Materials (SBOMs)**:

   - **Generation**: CycloneDX SBOMs are generated for software releases using supply-chain tooling declared in the project ([ADR 004](./004-development-tooling.md)): `cyclonedx-bom`, `spdx-tools`, `pip-audit`, `deptry`, `import-linter`.
   - **Transparency and Compliance**: SBOMs provide a detailed inventory of software components, including their versions, licenses, and known vulnerabilities, to enhance transparency and compliance with regulations like the Cyber Resilience Act (CRA).

### Implementation Strategy

1. **Integration of Nix**:

   - **Hermetic Builds**: every Nix-built application builds in a sealed sandbox with no network access, against hash-pinned inputs. Each ecosystem's dependency set is vendored by a fixed-output derivation from a committed lockfile before the build begins, so the package manager runs offline. The [ADR 058](./058-build-reproducibility-model.md) tiers distinguish provenance: Tier-1 apps are packaged by nixpkgs, Tier-2 built from source by Hop3, and Tier-3 wrap an upstream binary that is hash-pinned and not auditable.
   - **Content-addressed closures**: Every Nix-built app has a content-addressed closure whose full dependency graph is inspectable via `nix-store -qR`, and update deltas are minimal: only changed store paths transfer.

1. **CI/CD Pipeline Enhancements**:

   - **Security Scans**: Automated security scans are integrated into the CI pipeline to monitor for vulnerabilities and compliance issues.
   - **SBOM Inclusion**: SBOMs are generated and included in the release pipeline so that each release carries a detailed inventory of all components.

### Continuous Improvement

1. **Monitoring and Auditing**:

   - **Regular Audits**: Regular security audits and reviews of the software supply chain identify and mitigate potential risks.
   - **Performance Monitoring**: The performance and security of the CI/CD pipeline are continuously monitored to ensure they meet the highest standards of software supply chain security.

1. **Community Engagement**:

   - **Feedback Loop**: A feedback loop with users and contributors continuously improves supply chain security practices based on real-world usage and feedback.
   - **Documentation and Training**: Comprehensive documentation and training are provided to the community on best practices for supply chain security and the use of SBOMs.

## Consequences

### Benefits

- **Enhanced Security**: Improves the security and integrity of the software supply chain by ensuring all dependencies are transparent and verifiable.
- **Compliance**: Ensures compliance with industry standards and regulations such as the Cyber Resilience Act (CRA) through detailed SBOMs.
- **Transparency**: Increases transparency and trust by providing a comprehensive inventory of software components and their security status.

### Drawbacks

- **Implementation Effort**: Requires significant effort to integrate and maintain SBOM generation and supply chain security practices.
- **Complexity**: Adds complexity to the development and delivery pipeline, necessitating tools and processes to manage it effectively.

## Risks

- **Security Threats**: Ongoing risk of evolving security threats. Mitigation involves continuous monitoring, regular updates, and proactive security measures.
- **Toolchain Integration**: Potential challenges in integrating SBOM generation tools with the existing CI/CD pipeline. Mitigation includes thorough testing and community support.

## Future Work

- **Signature attestation** (Sigstore / in-toto / cosign) for release artefacts and for the SBOM itself, likely required for Cyber Resilience Act compliance.
- **Reproducible-builds verification on a schedule.** The rebuild check exists and covers all three tiers ([ADR 058](./058-build-reproducibility-model.md)). The remaining piece is a scheduler that runs it without being asked ([ADR 044](./044-nightly-test-lab.md)).
- **Upstream source mirroring** to insulate against PyPI / registry deletions.
