# ADR 016: Backup Strategy

- **Status**: Accepted
- **Type**: Feature
- **Created**: 2024-07-17
- **Related-ADRs**: [010](./010-security-and-resilience.md), [024](./024-backup-restore-system.md), [036](./036-cli-ergonomics.md)

## Context and Goals

Ensuring the availability and integrity of data is critical for the Hop3 platform. A backup strategy is essential to protect against data loss and corruption and to enable quick recovery after failures. The goal is to define a backup strategy that covers different types of data (e.g., configuration files, application data, and databases) and ensures that backups are taken regularly, stored securely, and can be restored efficiently.

This ADR defines the long-term vision for Hop3's backup capabilities. [ADR 024](024-backup-restore-system.md) specifies the foundational backup and restore system on which the later phases build.

## Decision

Hop3 implements a backup strategy that includes regular backups of critical data, secure storage of backup files, and efficient restoration procedures. This strategy encompasses application data, configuration files, and databases.

The strategy is delivered in phases, so that a usable foundation exists before the more operationally demanding capabilities (scheduling, remote storage, encryption, incremental backups) are layered on:

| Feature | Phase | ADR |
|---------|-------|-----|
| Manual full backups | Phase 1 | [ADR 024](./024-backup-restore-system.md) |
| Local storage | Phase 1 | [ADR 024](./024-backup-restore-system.md) |
| Checksum verification | Phase 1 | [ADR 024](./024-backup-restore-system.md) |
| Service-specific backups | Phase 1 | [ADR 024](./024-backup-restore-system.md) |
| Automated scheduled backups | Phase 2 | - |
| Retention policies | Phase 2 | - |
| Remote storage (S3, B2) | Phase 3 | - |
| Encryption | Phase 3 | - |
| Incremental backups | Phase 3 | - |
| Transaction log backups | Phase 3 | - |

## Key Components

### Backup Types and Frequency

**Phase 1** (specified in [ADR 024](./024-backup-restore-system.md)):
- Manual full backups on demand
- All application components in one backup

**Phase 2+**:

1. **Configuration Files**:
   - **Frequency**: Daily backups of configuration files such as `hop3.toml`.
   - **Retention**: Retain daily backups for 30 days and monthly backups for 12 months.

2. **Application Data**:
   - **Frequency**: Incremental backups daily and full backups weekly for application data.
   - **Retention**: Retain daily incremental backups for 30 days and weekly full backups for 6 months.

3. **Databases**:
   - **Frequency**: Daily backups of databases with transaction log backups every hour.
   - **Retention**: Retain daily backups for 30 days and monthly backups for 12 months.

### Backup Storage and Security

**Phase 1** (specified in [ADR 024](./024-backup-restore-system.md)):
- Local file-based storage only
- File permissions (600) for access control
- SHA256 checksums for integrity

**Phase 2+**:

1. **Storage Locations**:
   - **Local Storage**: Store backups locally on a dedicated backup server or storage device.
   - **Remote Storage**: Use remote storage solutions such as cloud storage providers (e.g., AWS S3, Google Cloud Storage, Backblaze B2) for redundancy and disaster recovery.

2. **Security Measures**:
   - **Encryption**: Encrypt all backup files at rest and in transit to protect data confidentiality (using Age or GPG).
   - **Access Control**: Restrict access to backup files to authorized personnel.

### Restoration Procedures

**Phase 1** (specified in [ADR 024](./024-backup-restore-system.md)):
- Manual restore via CLI (`hop3 backup restore`)
- Checksum verification before restore
- Service-specific restore (PostgreSQL via `pg_restore`, etc.)

**Phase 2+**:

1. **Regular Testing**:
   - **Test Restorations**: Regularly restore backups to verify that the files are intact and the procedure works.
   - **Documentation**: Maintain detailed documentation of the restoration procedures and update it regularly.

2. **Automated Restoration**:
   - **Automation Tools**: Use automated tools and scripts to speed up restoration.
   - **Monitoring**: Implement monitoring systems to detect and alert on backup failures.

### Continuous Improvement

1. **Feedback Loop**:
   - **User Feedback**: Ask users and administrators about the backup strategy and adjust it based on what we learn.
   - **Performance Monitoring**: Monitor the performance and reliability of the backup processes and fix issues as they appear.

2. **Community Engagement**:
   - **Hop3 Community**: Encourage contributions from the Hop3 community to improve the backup strategy.

## Consequences

### Benefits

- **Data Protection**: Protects the availability and integrity of critical data.
- **Quick Recovery**: Enables quick recovery after data loss or corruption.
- **Security**: Enhances security through encryption and strict access control measures (Phase 3).

### Drawbacks

- **Resource Intensive**: Requires storage resources and network bandwidth for regular backups.
- **Management Complexity**: Adds complexity to system management and needs careful planning and monitoring.
- **Phased Delivery**: The advanced capabilities (scheduling, remote storage, encryption, incremental backups) depend on operational machinery that the foundational phase does not provide, so they become available only as later phases are built.

## Risks

- **Backup Failures**: Backups can fail or produce corrupt archives. Mitigation involves regular testing and monitoring.
- **Security Breaches**: Risk of unauthorized access to backup files. Mitigation includes strong encryption (Phase 3) and access control measures.

## References

- **Implementation**: [ADR 024: Backup and Restore System](024-backup-restore-system.md)
- **Code**: `packages/hop3-server/src/hop3/core/backup.py`
- **User Docs**: `docs/src/backup-restore.md`
