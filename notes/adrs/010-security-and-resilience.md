# ADR 010: Security and Resilience (Umbrella)

**Status**: Accepted
**Type**: Feature
**Created**: 2024-07-17
**Related-ADRs**: 011, 012, 013, 014, 024, 029

## Purpose

This ADR is the landing page for Hop3's security and resilience design. It enumerates the sub-concerns and points at the ADRs that decide them. It does not, by itself, commit Hop3 to specific mechanisms; the concrete design for each concern lives in its child ADR. A broad-scope "implement encryption, RBAC, MFA, backups, monitoring" framing is deliberately rejected here: a security decision is only meaningful once it commits to a mechanism, so each mechanism is decided in its own ADR rather than asserted in the aggregate.

## Sub-concerns and child ADRs

| Concern | Child ADR |
|---------|-----------|
| Data encryption at rest (credentials, session data) | [ADR 011](011-encryption.md) |
| Multi-factor authentication | [ADR 012](012-mfa.md) |
| Software supply chain security, SBOM | [ADR 013](013-supply-chain.md) |
| Authentication bootstrap (first-admin provisioning) | [ADR 014](014-authentication-bootstrap.md) |
| Backup and restore | [ADR 024](024-backup-restore-system.md) |
| Reconciliation and health checks | [ADR 029](029-reconciliation-health-checks.md) |

## What is out of scope for this umbrella ADR

- Specific cryptographic primitives and rotation policies (→ ADR 011).
- MFA flow and device-registration UX (→ ADR 012).
- Supply-chain attestation mechanisms (→ ADR 013).
- First-admin and magic-link flows (→ ADR 014).
- Backup formats and scheduling (→ ADR 024).
- Multi-node resilience / failover. Hop3 targets single-host deployments; cross-host resilience is not in scope (see ADR 017 for the long-arc multi-node story).
- Formal compliance with GDPR / ISO 27001 / NIST. Operators are responsible for compliance of their own deployments; Hop3 provides the primitives (encryption, audit logging, backups) but does not certify compliance.

## Operational posture

The umbrella defines a baseline posture that the child ADRs refine:

- **Authentication**: JWT tokens issued on login; every RPC call is authenticated; bearer-token handling is case-insensitive per RFC 7235; session lifetime is configurable via `HOP3_TOKEN_EXPIRY_HOURS`.
- **Rate limiting**: An in-memory sliding-window limiter guards `/auth/login` and `/auth/magic/{token}` (5 requests per minute per IP).
- **Credentials at rest**: Fernet AEAD encryption with a server-side `HOP3_SECRET_KEY` (see ADR 011).
- **Audit**: Structured audit records for security-relevant events.
- **Transport**: HTTPS or SSH-tunnelled HTTP; no unencrypted RPC in production.
- **Health checks**: Per-app HTTP probing at the declared health-check path; a reconciliation loop is specified in ADR 029.
- **Backups**: Full backup and restore of app state and addon data (ADR 024).

An **external security review** precedes general release.
