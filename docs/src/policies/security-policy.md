# Hop3 Security Policy

**Last Updated:** 2025-06-17

## Introduction

Security is a foundational principle of the Hop3 project, deeply integrated into our core values of sovereignty, resilience, and trust. Our approach is proactive and transparent. We are committed to a "secure-by-design" philosophy, ensuring that security is considered at every stage of the development lifecycle.

This document outlines our security practices and provides guidelines for reporting vulnerabilities. We believe that a strong security posture is a collaborative effort, and we welcome the participation of our community and security researchers to help us protect our users.

## Scope

This policy applies to:

1.  **The Hop3 Software:** The source code and packaged releases of the Hop3 platform itself, available in our public repositories.
2.  **Project Infrastructure:** The official websites (e.g., `hop3.cloud`), documentation sites, and community platforms managed directly by the Hop3 project team.

This policy does not cover the applications you deploy on your self-hosted Hop3 instance or the security of your underlying server infrastructure, which remain your responsibility.

## Our Security Practices

We have implemented several measures to ensure the security and integrity of the Hop3 platform.

### Secure Software Development

-   **Code Reviews:** All code contributions are subject to review by project maintainers to identify potential security flaws, bugs, and deviations from best practices.
-   **Static Analysis Security Testing (SAST):** We use automated tools like `bandit` and `ruff` within our CI/CD pipeline to scan our Python codebase for common security vulnerabilities.
-   **Software Supply Chain Security:**
    -   We use tools like `safety` to check our dependencies against known vulnerability databases.
    -   We are committed to providing a Software Bill of Materials (SBOM) for our releases, ensuring full transparency of all included components and their licenses.
    -   Our integration with package managers like Nix aims to create deterministic, reproducible, and isolated build environments, significantly reducing supply chain risks.

### Infrastructure Security

-   **Access Control:** Access to our production infrastructure is strictly limited to authorized project maintainers on a need-to-know basis. Multi-Factor Authentication (MFA) is enforced where available.
-   **Encryption in Transit:** All communication with our official websites and services is encrypted using Transport Layer Security (TLS/SSL).
-   **Regular Patching:** Our infrastructure is regularly updated and patched to protect against known vulnerabilities in the operating system and other system-level software.

### Data Protection

We are committed to protecting any data we handle. For detailed information, please see our [**Privacy Policy**](./privacy-policy.md). Key measures include encryption at rest for sensitive data and secure backup procedures.

## Responsible Disclosure Policy

We take security vulnerabilities very seriously. If you believe you have found a security vulnerability in the Hop3 software or our project infrastructure, we ask that you report it to us privately to allow us time to investigate and remediate the issue.

### How to Report a Vulnerability

Please send a detailed report to our private security contact:

**Email: security@abilian.com**

Your report should include, if possible:

-   A clear description of the vulnerability, including its type and potential impact.
-   The component, version, and location where the vulnerability was discovered.
-   Step-by-step instructions to reproduce the issue (including any proof-of-concept code).
-   Any recommendations you have for a potential fix.

### Our Commitment to You

When you report a vulnerability to us in good faith, we commit to the following:

1.  **Timely Acknowledgment:** We will acknowledge receipt of your report, typically within 2 business days.
2.  **Dedicated Investigation:** We will promptly investigate your report and work to validate the vulnerability.
3.  **Open Communication:** We will maintain an open line of communication, keeping you informed of our progress.
4.  **Public Recognition:** Once the vulnerability is remediated, we will publicly credit you for your discovery, unless you prefer to remain anonymous.
5.  **Safe Harbor:** We will not take legal action against you or ask law enforcement to investigate you for your responsible, good-faith security research and reporting activities.

### Guidelines for Reporters

We ask that you act in good faith and adhere to the following guidelines:

-   **Do No Harm:** Do not attempt to access, modify, or destroy data that does not belong to you. Your research should not disrupt our services or impact other users.
-   **Provide Time to Remediate:** Do not disclose the vulnerability publicly until we have had a reasonable amount of time to investigate and deploy a fix.
-   **Act Ethically:** Avoid privacy violations, data destruction, and interruption or degradation of our services.

## Security Advisories

Once a vulnerability has been fixed and a patch is released, we will publish a security advisory. Advisories will be published through appropriate channels, which may include:

-   GitHub Security Advisories in the relevant repository.
-   A post on our official project blog or news section.
-   Notes in the official `CHANGELOG.md` for the corresponding release.

## Questions

If you have any questions about this Security Policy, please feel free to contact us at the email address listed above.
