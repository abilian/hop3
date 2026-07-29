# ADR 010: Security and Resilience (Umbrella)

- **Status**: Accepted
- **Type**: Feature
- **Created**: 2024-07-17
- **Related-ADRs**: [011](./011-encryption.md), [012](./012-mfa.md), [013](./013-supply-chain.md), [014](./014-authentication-bootstrap.md), [024](./024-backup-restore-system.md), [029](./029-reconciliation-health-checks.md)

## Purpose

This ADR is the landing page for Hop3's security and resilience design. The table below maps each sub-concern to its child ADR. Each concern commits to a specific mechanism in its own ADR; a broad-scope "implement encryption, RBAC, MFA, backups, monitoring" framing would short-circuit that: a security decision is only meaningful once it commits to a mechanism.

## Sub-concerns and child ADRs

| Concern | Child ADR |
|---------|-----------|
| Data encryption at rest (credentials, session data) | [ADR 011](011-encryption.md) |
| Multi-factor authentication | [ADR 012](012-mfa.md) |
| Software supply chain security, SBOM | [ADR 013](013-supply-chain.md) |
| Authentication bootstrap (first-admin provisioning) | [ADR 014](014-authentication-bootstrap.md) |
| Backup and restore | [ADR 024](024-backup-restore-system.md) |
| Reconciliation and health checks | [ADR 029](029-reconciliation-health-checks.md) |
| Network firewall and per-app port exposure | [ADR 040](040-network-firewall-and-port-exposure.md) |
| Privilege separation for root-only operations | [ADR 041](041-privileged-operations-agent.md) |
| Server configuration and secret storage | [ADR 048](048-server-config-and-secret-storage.md) |
| Layer-7 web application firewall | [ADR 050](050-waf-l7-lewaf.md) |
| App-runtime UID separation | [ADR 055](055-app-runtime-uid-separation.md) |
| App admin credentials (bootstrap, storage, retrieval) | [ADR 056](056-app-admin-credentials.md) |

The engineering companion to this ADR — the trust model, the catalogue of audited-and-deliberate patterns, and the procedure for running a review round — is `notes/security/security-model.md`. Published security policy and the vulnerability disclosure channel are in `docs/src/reference/policies/security-policy.md`.

## What is out of scope for this umbrella ADR

- Specific cryptographic primitives and rotation policies (→ [ADR 011](./011-encryption.md)).
- MFA flow and device-registration UX (→ [ADR 012](./012-mfa.md)).
- Supply-chain attestation mechanisms (→ [ADR 013](./013-supply-chain.md)).
- First-admin and magic-link flows (→ [ADR 014](./014-authentication-bootstrap.md)).
- Backup formats and scheduling (→ [ADR 024](./024-backup-restore-system.md)).
- Multi-node resilience / failover. Hop3 targets single-host deployments; cross-host resilience is not in scope (see [ADR 017](./017-agent-based-architecture.md) for the long-arc multi-node story).
- Formal compliance with GDPR / ISO 27001 / NIST. Operators are responsible for compliance of their own deployments; Hop3 provides the primitives (encryption, audit logging, backups) but does not certify compliance.

## Operational posture

- **Authentication**: JWT tokens issued on login; every RPC call is authenticated; bearer-token handling is case-insensitive per RFC 7235; session lifetime is configurable via `HOP3_TOKEN_EXPIRY_HOURS` (default 24 hours).
- **Authorization**: scope-based. Commands that manage users and accounts apply an admin check. Per-resource ownership is not modelled: the control plane is single-tenant, so an authenticated account is an operator-equivalent credential and reaches every app and addon on the host. Runtime isolation between apps is a separate mechanism and does hold ([ADR 055](./055-app-runtime-uid-separation.md), [ADR 046](./046-declarative-app-resources.md)). Per-resource ownership is planned; the reasoning is in `notes/security/security-model.md` §1.4.
- **Rate limiting**: An in-memory sliding-window limiter guards `/auth/login` and `/auth/magic/{token}` (5 requests per minute per IP). The limiter's state is per worker process, which is why the server runs single-worker.
- **Credentials at rest**: Fernet AEAD encryption with a key derived from the server-side `HOP3_SECRET_KEY` (see [ADR 011](./011-encryption.md)).
- **Audit**: `hop3-rootd` keeps an append-only audit log, with credential redaction and an `fsync` per entry, covering every privileged operation ([ADR 041](./041-privileged-operations-agent.md)). The control plane has no equivalent audit log for RPC-level security events; that gap is open.
- **Transport**: HTTPS or SSH-tunnelled HTTP; no unencrypted RPC in production.
- **Health checks**: Per-app HTTP probing at the declared health-check path; a reconciliation loop is specified in [ADR 029](./029-reconciliation-health-checks.md).
- **Backups**: Full backup and restore of app state and addon data ([ADR 024](./024-backup-restore-system.md)).

An **external security review** precedes general release.
