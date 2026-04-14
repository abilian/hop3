# ADR 011: Data Encryption and Protection

**Status**: Accepted (shipped posture; rotation / HSM deferred)
**Type**: Feature
**Created**: 2024-07-17
**Updated**: 2026-04-14
**Related-ADRs**: 010, 012, 013

## Revisions

- v0.2: Promoted from Draft to Accepted. The original Draft was too generic to validate; this revision replaces it with a concrete statement of what is shipped today and what remains future work (2026-04-14).
- v0.1: Initial draft (2024-07-17)

## Implementation Status

**Shipped posture (production use across the hop3-server control plane):**

- **Credentials at rest**: Addon credentials, session secrets, and magic-link tokens are encrypted with **Fernet AEAD** (AES-128-CBC + HMAC-SHA256) using a key derived from the server's `HOP3_SECRET_KEY` environment variable via **PBKDF2-HMAC-SHA256** (see `hop3/server/security/`).
- **Passwords**: User passwords hashed with **bcrypt** at cost factor 12 (see ADR 014).
- **JWT tokens**: Signed with HS256 against `HOP3_SECRET_KEY`; signature verification enforced on every RPC call.
- **Transport**: HTTPS or SSH-tunnelled HTTP only. No plaintext RPC in production.
- **Database at rest**: The control-plane SQLite/PostgreSQL file sits on the operator's host filesystem; Hop3 does not encrypt the file itself but relies on host-level protections (filesystem ACLs, optional full-disk encryption). Values the operator should not be able to read in plaintext (addon credentials, session secrets) are encrypted inside the row.

**Deferred (not blocking; tracked here for future work):**

- **Key rotation**: Manual rotation works (change `HOP3_SECRET_KEY`, re-encrypt); there is no automated rotation policy or secondary-key envelope scheme. A rotation-at-deploy-time mechanism is a candidate for post-0.6.
- **Hardware-backed key storage (HSM, TPM, cloud KMS)**: Not supported. `HOP3_SECRET_KEY` lives in the server's environment; operators who require hardware-backed key storage should integrate at the OS level (sealed systemd credentials, TPM-backed keyrings).
- **Database-file encryption**: Not provided by Hop3. Left to operator via host-level full-disk encryption.
- **Per-tenant encryption keys**: Not applicable — Hop3 is single-tenant per deployment.

## Context and Goals

Data protection is a critical aspect of securing the Hop3 platform. The goal is to ensure that all data handled by Hop3 is protected through robust encryption methods, both at rest and in transit. This will help protect sensitive information, comply with regulatory requirements, and build user trust.

## Decision

Hop3 will implement comprehensive data encryption strategies to protect data at rest and in transit. This includes using industry-standard encryption algorithms and ensuring that all sensitive data is encrypted to prevent unauthorized access and data breaches.

## Key Components

### Data Encryption

1. **Encryption at Rest**:

   - **Database Encryption**: Encrypt all sensitive data stored in databases using strong encryption algorithms.
   - **File System Encryption**: Ensure that files and backups are encrypted on disk.

1. **Encryption in Transit**:

   - **Transport Layer Security (TLS)**: Use TLS to encrypt data transmitted over networks to protect against interception and eavesdropping.
   - **Secure Communication Protocols**: Implement secure communication protocols for API interactions and data exchanges.

### Key Management

1. **Key Storage**:

   - **Secure Key Management**: Use secure key management solutions to store and manage encryption keys.
   - **Access Control**: Restrict access to encryption keys to authorized personnel only.

1. **Key Rotation**:

   - **Regular Key Rotation**: Implement a policy for regular rotation of encryption keys to limit the exposure of compromised keys.
   - **Automated Key Management**: Use automated tools to manage key rotation and ensure compliance with security policies.

## Consequences

### Benefits

- **Data Protection**: Ensures the confidentiality and integrity of sensitive data.
- **Compliance**: Meets regulatory requirements for data protection and encryption.
- **User Trust**: Enhances user trust by demonstrating a commitment to data security.

### Drawbacks

- **Performance Overhead**: Encryption and decryption processes may introduce performance overhead.
- **Complexity**: Managing encryption keys and ensuring proper implementation can add complexity.

## Risks

- **Key Management Failures**: Risks associated with improper key management. Mitigation involves using secure key management solutions and regular audits.
- **Encryption Performance**: Potential performance impact due to encryption. Mitigation includes optimizing encryption processes and using efficient algorithms.

## Action Items

1. **Implement Encryption**:

   - Apply encryption to all sensitive data at rest and in transit.
   - Ensure compliance with industry standards and best practices.

1. **Enhance Key Management**:

   - Use secure key management solutions and enforce strict access controls.
   - Implement regular key rotation policies.

1. **Documentation and Training**:

   - Provide documentation on encryption practices and key management.
   - Train personnel on data protection and encryption protocols.
