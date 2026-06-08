# ADR 013: Software Supply Chain Security and SBOMs

**Status**: Accepted (phased — partial shipped, automation deferred)
**Type**: Feature
**Created**: 2024-07-17
**Updated**: 2026-04-14
**Related-ADRs**: 006, 008, 010

## Revisions

- 2026-04-14: Accepted (phased) — clarified what is in place vs. what remains for the supply-chain posture.
- 2024-07-17: Initial draft.

## Implementation Status

**Shipped (contributes to the supply-chain posture today):**

- **Hermetic builds via Nix** for Tier-1 applications (ADR 008 reproducibility taxonomy): Go and Rust apps from nixpkgs build in a pure sandbox against hash-pinned inputs. Tier-2 applications (Python-venv, PHP-composer, Node-prebuilt, Ruby-bundler) use `__noChroot`, which weakens hermeticity; this is documented in ADR 008.
- **Content-addressed closures** for every Nix-built app: full dependency graph is inspectable via `nix-store -qR`; update deltas are minimal (only changed store paths transfer).
- **Supply-chain-aware tooling declared in the project** (ADR 004): `cyclonedx-bom`, `spdx-tools`, `pip-audit` (via Nox), `deptry`, `import-linter`.
- **REUSE-compliant license headers** on every source file, enforced in CI.

**Partial / in progress:**

- **SBOM emission per release**: tooling is available but not yet wired into the release pipeline. Manual `cyclonedx-py` invocation works; the CI target to attach an SBOM to each tagged release is not yet in place.
- **Dependency auditing**: `pip-audit` runs via Nox on demand; a scheduled CI run (weekly) is not yet configured.

**Deferred:**

- **Signature attestation** (Sigstore / in-toto / cosign) for release artefacts and for the SBOM itself. Likely required for Cyber Resilience Act compliance; not in scope for 0.6.
- **Reproducible-builds verification as a CI gate** (two independent rebuilds of each Tier-1 app, bit-compare).
- **Upstream source mirroring** to insulate against PyPI / registry deletions.

The **Genealogos** reference in the original Draft is retained as a candidate tool but is not a committed dependency; any SBOM generator producing valid CycloneDX output meets the requirement.

## Context and Goals

Ensuring the security of the software supply chain is critical to the integrity and reliability of the Hop3 platform. With increasing threats to software security, it is essential to adopt best practices that enhance the transparency, traceability, and security of software components. The goal is to implement robust measures for software supply chain security, including the use of Software Bill of Materials (SBOMs) to provide a detailed inventory of software components.

## Decision

Hop3 will adopt a proactive stance towards software supply chain security by integrating comprehensive SBOMs and rigorous security practices throughout the development and delivery pipeline. This will involve using tools like Genealogos to generate compliance-ready CycloneDX SBOMs, ensuring that all dependencies are transparent, verifiable, and secure.

## Key Components

### Software Supply Chain Security

1. **Dependency Management**:

   - **Nix Package Management**: Utilize Nix for deterministic builds and dependency management, ensuring that all software dependencies are explicitly defined, reproducible, and isolated.
   - **Dependency Auditing**: Regularly audit dependencies for known vulnerabilities using automated tools and maintain up-to-date security patches.

1. **Secure Development Practices**:

   - **Code Reviews**: Enforce thorough code reviews and security audits for all changes to the codebase.
   - **Continuous Integration**: Integrate security checks into the CI pipeline to automatically detect and address vulnerabilities early in the development process.

1. **Software Bill of Materials (SBOMs)**:

   - **Automatic Generation**: Use tools like Genealogos to automatically generate CycloneDX SBOMs for all software releases.
   - **Transparency and Compliance**: Ensure that SBOMs provide a detailed inventory of software components, including their versions, licenses, and known vulnerabilities, to enhance transparency and compliance with regulations like the Cyber Resilience Act (CRA).

### Implementation Strategy

1. **Integration of Nix**:

   - **Hermetic Builds**: Use Nix to ensure all builds are hermetic and reproducible, providing a consistent and secure environment for building and deploying applications.
   - **Reproducible Environments**: Leverage Nix's ability to create reproducible environments, minimizing the risk of dependency conflicts and security issues.

1. **CI/CD Pipeline Enhancements**:

   - **Security Scans**: Integrate automated security scans into the CI pipeline to continuously monitor for vulnerabilities and compliance issues.
   - **SBOM Inclusion**: Automatically generate and include SBOMs in the CI/CD pipeline, ensuring each release includes a detailed inventory of all components.

### Continuous Improvement

1. **Monitoring and Auditing**:

   - **Regular Audits**: Conduct regular security audits and reviews of the software supply chain to identify and mitigate potential risks.
   - **Performance Monitoring**: Continuously monitor the performance and security of the CI/CD pipeline to ensure it meets the highest standards of software supply chain security.

1. **Community Engagement**:

   - **Feedback Loop**: Establish a feedback loop with users and contributors to continuously improve supply chain security practices based on real-world usage and feedback.
   - **Documentation and Training**: Provide comprehensive documentation and training to the community on best practices for supply chain security and the use of SBOMs.

## Consequences

### Benefits

- **Enhanced Security**: Improves the security and integrity of the software supply chain by ensuring all dependencies are transparent and verifiable.
- **Compliance**: Ensures compliance with industry standards and regulations such as the Cyber Resilience Act (CRA) through detailed SBOMs.
- **Transparency**: Increases transparency and trust by providing a comprehensive inventory of software components and their security status.

### Drawbacks

- **Implementation Effort**: Requires significant effort to integrate and maintain SBOM generation and supply chain security practices.
- **Complexity**: Adds complexity to the development and delivery pipeline, necessitating robust tools and processes to manage it effectively.

## Risks

- **Security Threats**: Ongoing risk of evolving security threats. Mitigation involves continuous monitoring, regular updates, and proactive security measures.
- **Toolchain Integration**: Potential challenges in integrating SBOM generation tools with the existing CI/CD pipeline. Mitigation includes thorough testing and community support.
