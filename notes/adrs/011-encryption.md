# ADR 011: Data Encryption and Protection

- **Status**: Accepted
- **Type**: Feature
- **Created**: 2024-07-17
- **Related-ADRs**: [010](./010-security-and-resilience.md), [012](./012-mfa.md), [013](./013-supply-chain.md)

## Context and Goals

Hop3 must protect the data it handles through encryption at rest and in transit. This protects sensitive information, helps comply with regulatory requirements, and builds user trust.

The control plane handles several classes of sensitive data (addon credentials, session secrets, magic-link tokens, user passwords, and RPC traffic) each with different protection requirements. The design must state, concretely, how each class is protected and where the protection boundary lies between Hop3 and the operator's host.

## Decision

Hop3 protects data at rest and in transit using industry-standard encryption algorithms, encrypting sensitive data to prevent unauthorized access and data breaches. The protection posture is defined per data class, and the boundary between platform-provided encryption and operator-provided host protection is made explicit.

## Detailed Design

### Encryption at Rest

- **Credentials and secrets**: Addon credentials, session secrets, and magic-link tokens are encrypted with **Fernet AEAD** (AES-128-CBC + HMAC-SHA256). The key is derived from the server's `HOP3_SECRET_KEY` environment variable via **PBKDF2-HMAC-SHA256**. The encryption routines live in `hop3/server/security/`.
- **Passwords**: User passwords are hashed with **bcrypt** at cost factor 12 (see [ADR 014](./014-authentication-bootstrap.md)).
- **Database file**: The control-plane SQLite/PostgreSQL file sits on the operator's host filesystem. Hop3 does not encrypt the file itself; it relies on host-level protections (filesystem ACLs, optional full-disk encryption). Values the operator should not be able to read in plaintext (addon credentials, session secrets) are encrypted inside the row. This draws the boundary deliberately: row-level encryption protects secrets even from an operator with read access to the database, while file-level confidentiality is the operator's responsibility.

### Encryption in Transit

- **Transport**: RPC traffic travels over HTTPS or SSH-tunnelled HTTP only. No plaintext RPC is permitted in production.
- **JWT tokens**: Tokens are signed with HS256 against `HOP3_SECRET_KEY`, and signature verification is enforced on every RPC call.

### Key Management

- **Key storage**: `HOP3_SECRET_KEY` lives in the server's environment. Access is restricted to the server process. Operators who require hardware-backed key storage integrate at the OS level (sealed systemd credentials, TPM-backed keyrings); Hop3 does not embed an HSM, TPM, or cloud KMS dependency.
- **Key rotation**: Rotation is performed manually by changing `HOP3_SECRET_KEY` and re-encrypting the affected values.

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
- **Per-tenant encryption keys**: Not applicable: Hop3 is single-tenant per deployment.
