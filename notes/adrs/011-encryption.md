# ADR 011: Data Encryption and Protection

- **Status**: Accepted
- **Type**: Feature
- **Created**: 2024-07-17
- **Related-ADRs**: [010](./010-security-and-resilience.md), [012](./012-mfa.md), [013](./013-supply-chain.md)

## Context and Goals

Hop3 must protect the data it handles through encryption at rest and in transit. This protects sensitive information and helps meet regulatory requirements.

The control plane handles several classes of sensitive data (addon credentials, session secrets, magic-link tokens, user passwords, and RPC traffic) each with different protection requirements. The design must state, concretely, how each class is protected and where the protection boundary lies between Hop3 and the operator's host.

## Decision

Hop3 encrypts sensitive data at rest and in transit. The protection posture is defined per data class, and the boundary between platform-provided encryption and operator-provided host protection is made explicit.

## Detailed Design

### Encryption at Rest

- **Credentials and secrets**: Addon credentials, app admin credentials, session secrets, and magic-link tokens are encrypted with **Fernet AEAD** (AES-128-CBC + HMAC-SHA256). The key is derived from the server's `HOP3_SECRET_KEY` environment variable via **PBKDF2-HMAC-SHA256**. The encryption routines live in `hop3/core/credentials.py`.
- **Versioned key derivation**: the derivation parameters are a versioned scheme, so they can be strengthened without stranding existing installs. The current scheme (**v2**, stored with a `v2:` token prefix) uses 600,000 iterations (the OWASP 2026 baseline) with a per-install salt from `HOP3_CREDENTIAL_SALT`. The legacy scheme (**v1**, unprefixed) used 100 000 iterations and a static salt; it remains readable, and `hop3 admin reencrypt-credentials` migrates stored values forward. A weaker legacy scheme is migrated rather than silently tolerated.
- **Passwords**: User passwords are hashed with **bcrypt** at cost factor 12 (see [ADR 014](./014-authentication-bootstrap.md)).
- **Database file**: The control-plane SQLite/PostgreSQL file sits on the operator's host filesystem. Hop3 does not encrypt the file itself; it relies on host-level protections (filesystem ACLs, optional full-disk encryption). Values the operator should not be able to read in plaintext (addon credentials, session secrets) are encrypted inside the row. Row-level encryption protects secrets even from an operator with read access to the database; file-level confidentiality is the operator's responsibility.

### Encryption in Transit

- **Transport**: RPC traffic travels over HTTPS or SSH-tunnelled HTTP only. No plaintext RPC is permitted in production.
- **JWT tokens**: Tokens are signed with HS256 against `HOP3_SECRET_KEY`, and signature verification is enforced on every RPC call.

### Key Management

- **Key storage**: `HOP3_SECRET_KEY` lives in the server's environment. Access is restricted to the server process. Operators who require hardware-backed key storage integrate at the OS level (sealed systemd credentials, TPM-backed keyrings); Hop3 does not embed an HSM, TPM, or cloud KMS dependency.
- **Key rotation**: Rotation is manual and operator-driven: change `HOP3_SECRET_KEY`, then re-encrypt the affected values. `hop3 admin reencrypt-credentials` performs the re-encryption pass (with `--dry-run`); the operator-facing procedure is in the security policy. There is no automated or scheduled rotation.

## Consequences

### Benefits

- **Data Protection**: Ensures the confidentiality and integrity of sensitive data, including against an operator with raw database read access.
- **Compliance**: Meets regulatory requirements for data protection and encryption.
- **User Trust**: Demonstrates a commitment to data security.

### Drawbacks

- **Performance Overhead**: Encryption, decryption, and password hashing introduce performance overhead.
- **Complexity**: Managing encryption keys and ensuring correct implementation adds complexity.

## Risks

- **Key Management Failures**: Improper key management is the dominant risk. Mitigation relies on restricting access to `HOP3_SECRET_KEY` and on regular audits.
- **Encryption Performance**: Encryption may impact performance. Mitigation includes efficient algorithm choices and bounding hashing cost (bcrypt cost factor 12).

## Non-Goals and Boundaries

- **Automated key rotation**: There is no automated rotation policy or secondary-key envelope scheme; rotation is manual.
- **Hardware-backed key storage (HSM, TPM, cloud KMS)**: Not provided by Hop3. Operators requiring it integrate at the OS level.
- **Database-file encryption**: Not provided by Hop3. The operator supplies host-level full-disk encryption.
- **Per-tenant encryption keys**: One key per deployment, not one per account. Hop3's control plane is single-tenant: an authenticated account is operator-equivalent and reaches every app on the host, so deriving a key per account would protect nothing the authorization layer does not already grant. The reasoning and its consequences for reviewers are in `notes/security/security-model.md` §1.4. Per-resource ownership is planned; when the control plane distinguishes accounts, per-tenant key derivation becomes a question this ADR reopens.
