# ADR 010: Security and Resilience (Umbrella)

**Status**: Accepted (umbrella — individual concerns tracked in child ADRs)
**Type**: Feature
**Created**: 2024-07-17
**Updated**: 2026-04-14
**Related-ADRs**: 011, 012, 013, 014, 024, 029

## Revisions

- v0.2: Reframed from a broad-scope "implement security and resilience" ADR into an umbrella pointing to the individual ADRs that carry the real decisions. The original v0.1 was too generic to validate (it listed "implement encryption, implement RBAC, implement MFA, implement backups, implement monitoring" without committing to any mechanism). The concrete design and status live in the child ADRs below (2026-04-14).
- v0.1: Initial draft (2024-07-17)

## Purpose

This ADR serves as the landing page for Hop3's security and resilience design. It exists to enumerate the sub-concerns and point at the ADRs that decide them. It does not, by itself, commit Hop3 to specific mechanisms.

## Sub-concerns and child ADRs

| Concern | Child ADR | Status |
|---------|-----------|--------|
| Data encryption at rest (credentials, session data) | [ADR 011](011-encryption.md) | Draft — shipped in practice via Fernet AEAD + PBKDF2-HMAC-SHA256; ADR to be promoted when reviewed. |
| Multi-factor authentication | [ADR 012](012-mfa.md) | Draft — not yet shipped; post-0.6. |
| Software supply chain security, SBOM | [ADR 013](013-supply-chain.md) | Draft — SBOM tooling (cyclonedx-bom, spdx-tools) declared in ADR 004; SBOM emission not yet automated. |
| Authentication bootstrap (first-admin provisioning) | [ADR 014](014-authentication-bootstrap.md) | Final — shipped. |
| Backup and restore | [ADR 024](024-backup-restore-system.md) | Final — shipped (initial scope per ADR 016). |
| Reconciliation and health checks | [ADR 029](029-reconciliation-health-checks.md) | Draft — agent loop scheduled for 0.6. |

## What is out of scope for this umbrella ADR

- Specific cryptographic primitives and rotation policies (→ ADR 011).
- MFA flow and device-registration UX (→ ADR 012).
- Supply-chain attestation mechanisms (→ ADR 013).
- First-admin and magic-link flows (→ ADR 014).
- Backup formats and scheduling (→ ADR 024).
- Multi-node resilience / failover. Hop3 targets single-host deployments; cross-host resilience is not in scope (see ADR 017 for the long-arc multi-node story).
- Formal compliance with GDPR / ISO 27001 / NIST. Operators are responsible for compliance of their own deployments; Hop3 provides the primitives (encryption, audit logging, backups) but does not certify compliance.

## Operational posture

The current shipped posture, to be refined as child ADRs mature:

- **Authentication**: JWT tokens issued on login; every RPC call authenticated; bearer-token handling is case-insensitive per RFC 7235; session lifetime configurable via `HOP3_TOKEN_EXPIRY_HOURS`.
- **Rate limiting**: In-memory sliding-window limiter on `/auth/login` and `/auth/magic/{token}` (5 requests per minute per IP).
- **Credentials at rest**: Fernet AEAD encryption with a server-side `HOP3_SECRET_KEY` (see ADR 011).
- **Audit**: Structured audit records for security-relevant events.
- **Transport**: HTTPS or SSH-tunnelled HTTP; no unencrypted RPC in production.
- **Health checks**: Per-app HTTP probing at the declared health-check path; reconciliation loop (ADR 029) is scheduled work.
- **Backups**: Full backup and restore of app state and addon data (ADR 024).

An **external security review** is scheduled before release 0.6.
