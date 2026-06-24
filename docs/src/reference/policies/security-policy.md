# Hop3 Security Policy

**Last Updated:** 2026-06-20

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
-   **Static Analysis Security Testing (SAST):** Our linter `ruff` runs the `flake8-bandit` (`S`) ruleset to scan our Python codebase for common security vulnerabilities as part of our automated quality checks.
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

### Service Credential Encryption

#### HOP3_SECRET_KEY Requirement

Hop3 stores backing service credentials (databases, caches, etc.) encrypted at rest using industry-standard encryption. This requires a secret key configured via the `HOP3_SECRET_KEY` environment variable.

**Encryption Details:**
- **Algorithm:** Fernet (symmetric AEAD - Authenticated Encryption with Associated Data)
- **Key Derivation:** PBKDF2-HMAC-SHA256 with 600,000 iterations (OWASP 2026 baseline), using a per-install salt
- **Storage:** Credentials encrypted in the Hop3 database (SQLite or PostgreSQL)
- **Security Properties:**
  - Authenticated encryption (tampering detected automatically)
  - Database backups safe (cannot decrypt without secret key)
  - Thread-safe encryption operations
  - URL-safe base64 encoding

**Generating HOP3_SECRET_KEY:**

Generate a strong, cryptographically secure secret key:

```bash
# Using Python (recommended)
python3 -c "import secrets; print(secrets.token_urlsafe(32))"

# Using OpenSSL
openssl rand -base64 32
```

**Configuration:**

Set the environment variable before starting the Hop3 server. The production installer writes it to the systemd environment file `/etc/default/hop3` as a flat `KEY=value` line:

```bash
# In /etc/default/hop3 (loaded by the hop3-server systemd unit)
HOP3_SECRET_KEY=your-generated-secret-key-here
```

Equivalently, you can set it directly in the systemd service unit:

```ini
[Service]
Environment="HOP3_SECRET_KEY=your-generated-secret-key-here"
```

⚠️ **CRITICAL SECURITY REQUIREMENTS** ⚠️

**DO:**
- ✅ Generate a unique secret key for each Hop3 installation
- ✅ Use a cryptographically secure random generator (as shown above)
- ✅ Store the secret key securely (e.g., in environment files with restricted permissions)
- ✅ Back up the secret key securely (you cannot decrypt credentials without it)
- ✅ Restrict file permissions on configuration files containing the key (e.g., `chmod 600`)
- ✅ Use a key length of at least 32 bytes (256 bits)

**DO NOT:**
- ❌ Use weak or predictable values (e.g., "password", "secret123")
- ❌ Commit the secret key to version control
- ❌ Share the secret key across multiple Hop3 installations
- ❌ Store the key in publicly readable files
- ❌ Transmit the key over insecure channels
- ❌ Lose the secret key (credentials cannot be recovered)

**Key Rotation:**

If you need to rotate your encryption key:

1. Generate a new secret key
2. Before changing HOP3_SECRET_KEY, re-attach all services to apps (this re-encrypts with the old key)
3. Update HOP3_SECRET_KEY to the new key
4. Re-attach all services again (this re-encrypts with the new key)

Alternatively, for a fresh start:
1. Detach all services from all apps
2. Update HOP3_SECRET_KEY
3. Re-attach all services

**Impact of Lost Secret Key:**

If you lose your HOP3_SECRET_KEY:
- Existing service credentials cannot be decrypted
- You must detach and re-attach all services to generate new credentials
- This is a breaking change requiring service reconfiguration

**Backup Recommendations:**

- Include HOP3_SECRET_KEY in your secure backup procedures
- Store the key separately from database backups
- Use a secrets management system (e.g., HashiCorp Vault, AWS Secrets Manager) for production deployments
- Document the key location in your disaster recovery procedures

### Testing Mode Security

#### HOP3_UNSAFE Mode

For automated testing purposes, Hop3 includes a `HOP3_UNSAFE` configuration option that **completely disables authentication and authorization**. This mode exists solely to simplify automated testing in isolated Docker containers.

⚠️ **CRITICAL SECURITY WARNING** ⚠️

**What HOP3_UNSAFE Does:**
- Bypasses all authentication checks
- Grants full admin access to all requests
- Treats all requests as authenticated admin users
- Disables JWT token validation
- Disables command-level authorization

**Acceptable Use:**
- ✅ Automated tests running in isolated Docker containers
- ✅ Local development in completely isolated environments
- ✅ CI/CD pipelines with network-isolated test containers

**NEVER Use In:**
- ❌ Production servers
- ❌ Staging servers
- ❌ Any server accessible from a network
- ❌ Any shared development environment
- ❌ Any environment with real user data

**How to Verify It's Disabled:**

Before deploying any Hop3 instance to a network-accessible environment:

```bash
# Check environment variables (including the systemd environment file)
env | grep HOP3_UNSAFE          # Should return nothing or "false"
grep -i HOP3_UNSAFE /etc/default/hop3  # Should not exist or be "false"

# Check the server configuration file
grep -i HOP3_UNSAFE /home/hop3/hop3-server.toml  # Should not exist or be "false"

# Test that authentication is enforced. The JSON-RPC method is always "cli";
# the actual command goes in params.cli_args.
curl http://your-server/rpc -X POST \
  -H "Content-Type: application/json" \
  -d '{"method":"cli","params":{"cli_args":["app","list"],"extra_args":{}}}'
# Should return 401 Unauthorized
```

**Configuration:**

HOP3_UNSAFE can be enabled via:

1. Environment variable:
```bash
export HOP3_UNSAFE=true  # ONLY in isolated test containers
```

2. Configuration file (`hop3-server.toml`), as a flat top-level key:
```toml
HOP3_UNSAFE = "true"  # ONLY in isolated test containers
```

Two startup interlocks guard this flag:

- **Acknowledgement required:** enabling `HOP3_UNSAFE` also requires `HOP3_UNSAFE_ACK=yes-I-understand`. Without it the server refuses to start, so a stray env file or systemd drop-in cannot silently activate the bypass.
- **Production override:** when `MODE` is `production` (the default), `HOP3_UNSAFE` is forced off at startup and the event is logged at CRITICAL. The auth bypass therefore has no effect in production even if it is requested.

**Our Commitment:**

- HOP3_UNSAFE is **only** documented in testing and security documentation
- Installation scripts **never** enable HOP3_UNSAFE
- Default configuration files **never** include HOP3_UNSAFE
- The codebase includes explicit warning comments wherever HOP3_UNSAFE is checked
- Any production deployment guide explicitly warns against enabling HOP3_UNSAFE

## Responsible Disclosure Policy

We take security vulnerabilities seriously. If you believe you have found a security vulnerability in the Hop3 software or our project infrastructure, we ask that you report it to us privately to allow us time to investigate and remediate the issue.

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
-   Notes in the official `CHANGES.md` for the corresponding release.

## Questions

If you have any questions about this Security Policy, please feel free to contact us at the email address listed above.
