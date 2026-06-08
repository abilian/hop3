# ADR 016: Backup Strategy

**Status**: Accepted (phased — Phase 1 shipped via ADR 024; Phases 2–3 deferred)
**Type**: Feature
**Created**: 2024-07-17
**Updated**: 2026-04-22
**Related-ADRs**: 010, 024, 036

## Revisions

- v0.3: CLI example migrated from colon syntax (`hop3 backup:restore`) to space form (`hop3 backup restore`) per ADR 036 (2026-04-22).
- v0.2: Promoted from Draft to Accepted (phased). Phase 1 (manual full backups, local storage, checksum verification, per-service support) is delivered via ADR 024 (Final). This ADR captures the long-term vision; scheduled / remote / encrypted / incremental backups remain explicit future work (2026-04-14).
- v0.1: Initial draft (2024-07-17)

## Context and Goals

Ensuring the availability and integrity of data is critical for the Hop3 platform. A robust backup strategy is essential to protect against data loss, corruption, and ensure quick recovery in case of failures. The goal is to define a comprehensive backup strategy that covers different types of data (e.g., configuration files, application data, and databases) and ensures that backups are performed regularly, stored securely, and can be restored efficiently.

**Note**: This ADR defines the **long-term vision** for Hop3's backup capabilities. See [ADR 024](024-backup-restore-system.md) for the current implementation, which represents Phase 1 of this strategy.

## Decision

Hop3 will implement a comprehensive backup strategy that includes regular backups of critical data, secure storage of backup files, and efficient restoration procedures. This strategy will encompass application data, configuration files, and databases.

The implementation is phased:

| Feature | Phase | ADR |
|---------|-------|-----|
| Manual full backups | Phase 1 | ADR 024 |
| Local storage | Phase 1 | ADR 024 |
| Checksum verification | Phase 1 | ADR 024 |
| Service-specific backups | Phase 1 | ADR 024 |
| Automated scheduled backups | Phase 2 | - |
| Retention policies | Phase 2 | - |
| Remote storage (S3, B2) | Phase 3 | - |
| Encryption | Phase 3 | - |
| Incremental backups | Phase 3 | - |
| Transaction log backups | Phase 3 | - |

## Key Components

### Backup Types and Frequency

**Phase 1 (Current - ADR 024)**:
- Manual full backups on demand
- All application components in one backup

**Phase 2+ (Future)**:

1. **Configuration Files**:
   - **Frequency**: Daily backups of configuration files such as `hop3.toml` and other relevant configurations.
   - **Retention**: Retain daily backups for 30 days and monthly backups for 12 months.

2. **Application Data**:
   - **Frequency**: Incremental backups daily and full backups weekly for application data.
   - **Retention**: Retain daily incremental backups for 30 days and weekly full backups for 6 months.

3. **Databases**:
   - **Frequency**: Daily backups of databases with transaction log backups every hour.
   - **Retention**: Retain daily backups for 30 days and monthly backups for 12 months.

### Backup Storage and Security

**Phase 1 (Current - ADR 024)**:
- Local file-based storage only
- File permissions (600) for access control
- SHA256 checksums for integrity

**Phase 2+ (Future)**:

1. **Storage Locations**:
   - **Local Storage**: Store backups locally on a dedicated backup server or storage device.
   - **Remote Storage**: Use remote storage solutions such as cloud storage providers (e.g., AWS S3, Google Cloud Storage, Backblaze B2) for redundancy and disaster recovery.

2. **Security Measures**:
   - **Encryption**: Encrypt all backup files at rest and in transit to ensure data confidentiality (using Age or GPG).
   - **Access Control**: Implement strict access control measures to restrict access to backup files to authorized personnel only.

### Restoration Procedures

**Phase 1 (Current - ADR 024)**:
- Manual restore via CLI (`hop3 backup restore`)
- Checksum verification before restore
- Service-specific restore (PostgreSQL via `pg_restore`, etc.)

**Phase 2+ (Future)**:

1. **Regular Testing**:
   - **Test Restorations**: Perform regular test restorations to ensure that backup files are not corrupted and can be restored successfully.
   - **Documentation**: Maintain detailed documentation of the restoration procedures and update it regularly.

2. **Automated Restoration**:
   - **Automation Tools**: Use automated tools and scripts to facilitate quick and efficient restoration of backups.
   - **Monitoring**: Implement monitoring systems to detect and alert on backup failures or issues.

### Continuous Improvement

1. **Feedback Loop**:
   - **User Feedback**: Establish a feedback loop with users and administrators to continuously improve the backup strategy based on real-world usage and feedback.
   - **Performance Monitoring**: Monitor the performance and reliability of the backup processes to identify and address any issues promptly.

2. **Community Engagement**:
   - **Hop3 Community**: Encourage contributions from the Hop3 community to refine and enhance the backup strategy.

## Consequences

### Benefits

- **Data Protection**: Ensures the availability and integrity of critical data.
- **Quick Recovery**: Facilitates quick recovery in case of data loss or corruption.
- **Security**: Enhances security through encryption and strict access control measures (Phase 3).

### Drawbacks

- **Resource Intensive**: Requires significant storage resources and network bandwidth for regular backups.
- **Management Complexity**: Adds complexity to system management, requiring careful planning and monitoring.
- **Phased Delivery**: Full feature set not immediately available.

## Risks

- **Backup Failures**: Potential risk of backup failures or corruption. Mitigation involves regular testing and monitoring.
- **Security Breaches**: Risk of unauthorized access to backup files. Mitigation includes strong encryption (Phase 3) and access control measures.

## References

- **Implementation**: [ADR 024: Backup and Restore System](024-backup-restore-system.md)
- **Code**: `packages/hop3-server/src/hop3/core/backup.py`
- **User Docs**: `docs/src/backup-restore.md`
