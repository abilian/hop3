# ADR 024: Backup and Restore System

**Status**: Accepted
**Type**: Feature
**Created**: 2025-11-08
**Related-ADRs**: 016, 020

## Relationship to ADR 016

This ADR describes the **Phase 1 implementation** of Hop3's backup system. [ADR 016](016-backups.md) defines the long-term backup strategy including features planned for future phases (automated scheduling, remote storage, encryption, incremental backups). This ADR focuses on the foundational implementation that enables those future enhancements.

## Context

Hop3 needs a comprehensive backup and restore system to protect user applications and data. This is essential for:

1. **Disaster Recovery**: Quickly recover from server failures, data corruption, or accidental deletions
2. **Deployment Safety**: Allow rollback to previous versions if deployments fail
3. **Application Cloning**: Enable creating staging/test environments from production
4. **Migration**: Facilitate moving applications between servers
5. **User Confidence**: Give users peace of mind that their data is protected

The backup system must be:
- **Complete**: Capture all necessary data (code, data, config, services)
- **Reliable**: Ensure data integrity with verification
- **Simple**: Easy to use via CLI commands
- **Efficient**: Minimize storage use and backup time
- **Extensible**: Support future enhancements (encryption, remote storage, etc.)

## Decision

We have implemented a **file-based backup system** with the following design:

### Backup Format

Each backup is stored as a **directory** containing:

```
/var/hop3/backups/apps/<app-name>/<backup-id>/
├── metadata.json         # Backup manifest with checksums
├── source.tar.gz        # Git repository archive
├── data.tar.gz          # Application data archive
├── env.json             # Environment variables (JSON)
└── services/            # Service-specific backups
    └── postgres_<name>.sql
```

### Key Design Choices

1. **Directory-Based Storage**
   - Each backup is a self-contained directory
   - Easy to inspect, verify, and manage manually if needed
   - Simplifies integrity checking (each file has independent checksum)
   - Alternative considered: Single archive file (rejected - harder to inspect/verify)

2. **Tar.gz Compression**
   - Standard, well-supported format
   - Good compression ratio (typically 50-80%)
   - Fast compression/decompression
   - Can stream large files without loading into memory
   - Alternative considered: zip (rejected - less efficient), xz (rejected - slower)

3. **JSON Metadata**
   - Human-readable and inspectable
   - Standard format with excellent tooling
   - Easy to parse and validate
   - Contains complete inventory with checksums
   - Alternative considered: Binary format (rejected - not human-readable)

4. **SHA256 Checksums**
   - Industry-standard cryptographic hash
   - Detects any file corruption or tampering
   - Fast to compute
   - Stored in metadata.json for each file
   - Alternative considered: MD5 (rejected - cryptographically broken), SHA512 (rejected - overkill)

5. **Service Plugin Integration**
   - Leverages existing `Addon` protocol
   - Each service implements `backup()` and `restore()` methods
   - Service-specific backup format (e.g., PostgreSQL uses `pg_dump`)
   - Extensible: new services automatically support backup
   - Alternative considered: Generic service backup (rejected - loses service-specific optimizations)

6. **Unique Backup IDs**
   - Format: `YYYYMMDD_HHMMSS_<random-6-chars>`
   - Sortable by creation time
   - Collision-resistant (random suffix)
   - Human-readable timestamp
   - Alternative considered: UUID (rejected - not human-friendly), sequential numbers (rejected - not globally unique)

### Metadata Schema

The `metadata.json` includes:

```json
{
  "backup_id": "20251108_143022_a8f3d9",
  "app_name": "my-app",
  "created_at": "2025-11-08T14:30:22Z",
  "format_version": "1.0",
  "hop3_version": "0.8.0",
  "size_bytes": 15728640,
  "checksums": {
    "source.tar.gz": "sha256:abc123...",
    "data.tar.gz": "sha256:def456...",
    "env.json": "sha256:ghi789..."
  },
  "app_metadata": {
    "hostname": "myapp.example.com",
    "port": 8000,
    "run_state": "RUNNING"
  },
  "services": [
    {
      "type": "postgres",
      "name": "my-database",
      "backup_file": "services/postgres_my-database.sql",
      "size_bytes": 5242880,
      "checksum": "sha256:jkl012..."
    }
  ],
  "env_vars_count": 12,
  "expires_after": 0
}
```

### Database Integration

Backups are tracked in the database via the existing `Backup` model:

```python
class Backup(BigIntAuditBase):
    app_id: int
    state: BackupStateEnum  # SCHEDULED/STARTED/COMPLETED/FAILED
    remote_path: str        # Path to backup directory
    size: int              # Total size in bytes
    expires_after: int     # Retention time (0 = never)
```

This provides:
- State tracking for backup operations
- Integration with Hop3's audit trail
- Future support for scheduled backups
- Retention policy enforcement (future)

## Consequences

### Positive

1. **Simple and Transparent**
   - Users can inspect backups with standard tools
   - Easy to debug issues
   - No proprietary formats

2. **Reliable**
   - SHA256 checksums ensure integrity
   - Atomic operations prevent partial backups
   - Verification before restore

3. **Complete**
   - Captures all application components
   - Includes service data
   - Preserves environment variables

4. **Extensible**
   - Easy to add new backup targets
   - Service plugins handle service-specific logic
   - Metadata format supports versioning

5. **Efficient**
   - Compression reduces storage
   - Streaming for large files
   - No unnecessary copies

### Negative

1. **Local Storage Only**
   - Currently no remote backup support
   - Mitigated by: Future enhancement (S3, B2, etc.)

2. **No Encryption**
   - Environment variables stored in plaintext
   - Mitigated by: File permissions (600), future encryption support

3. **No Incremental Backups**
   - All backups are full backups
   - Mitigated by: Good compression, future incremental support

4. **Manual Retention**
   - No automatic cleanup
   - Mitigated by: Simple delete command, future automated policies

### Trade-offs

1. **Directory vs Single Archive**
   - Chose: Directory-based
   - Trade-off: Slightly more complex to copy (many files vs one)
   - Benefit: Much easier to inspect and verify

2. **JSON vs Binary Metadata**
   - Chose: JSON
   - Trade-off: Slightly larger size
   - Benefit: Human-readable, debuggable

3. **Service-Specific vs Generic Backup**
   - Chose: Service-specific (via Addon)
   - Trade-off: Each service needs backup implementation
   - Benefit: Optimal backup format per service (e.g., PostgreSQL dump vs Redis RDB)

## Alternatives Considered

### Single Archive File

**Considered:** Store entire backup as one `.tar.gz` file

**Rejected because:**
- Harder to inspect contents
- Must extract everything to verify one file
- Checksumming less granular
- Harder to implement partial restore (future)

### Database-Stored Backups

**Considered:** Store backup data in PostgreSQL/SQLite

**Rejected because:**
- BLOB storage inefficient
- Harder to move/copy backups
- Potential database bloat
- Backup system should not depend on database

### Cloud-First Approach

**Considered:** Store backups directly in S3/B2

**Rejected for initial version because:**
- Adds complexity and dependencies
- Requires configuration (API keys, etc.)
- Not all users have cloud access
- Can be added as enhancement

### Incremental Backups

**Considered:** Store only changed files since last backup

**Rejected for initial version because:**
- Significantly more complex
- Requires reference to previous backup
- Harder to verify integrity
- Can be added as enhancement

### Encrypted Backups

**Considered:** Encrypt all backup files

**Rejected for initial version because:**
- Adds key management complexity
- Not all users need encryption
- Can be added as opt-in enhancement

## Implementation Notes

### Code Organization

- **Core Logic:** `hop3/core/backup.py` - BackupManager class
- **Commands:** `hop3/commands/backup.py` - CLI commands
- **Models:** `hop3/orm/backup.py` - Database schema
- **Config:** `hop3/config.py` - BACKUP_ROOT path

### Testing Strategy

- **Unit Tests:** BackupManifest, checksums, ID generation
- **Integration Tests:** All CLI commands with mocked filesystem
- **System Tests:** Real PostgreSQL in Docker (future)
- **E2E Tests:** Complete workflows in production-like environment

### Service Integration

Services must implement:

```python
class Addon(Protocol):
    def backup(self) -> Path:
        """Create backup, return path to backup file."""
        ...

    def restore(self, backup_path: Path) -> None:
        """Restore from backup file."""
        ...
```

PostgreSQL example:

```python
def backup(self) -> Path:
    backup_file = backup_dir / f"{self.addon_name}_{timestamp}.sql"
    subprocess.run([
        "pg_dump", "-h", "localhost",
        "-U", self.db_user, "-d", self.db_name,
        "-f", str(backup_file)
    ], env={"PGPASSWORD": self.db_password})
    return backup_file
```

## Future Enhancements

1. **Automated Backups** (Phase 2)
   - Scheduled backups with cron-like syntax
   - Configurable in `hop3.toml`
   - Retention policies with automatic cleanup

2. **Remote Storage** (Phase 3)
   - S3, Backblaze B2, Azure Blob support
   - Pluggable storage backends
   - Automatic replication

3. **Encryption** (Phase 3)
   - Age or GPG encryption
   - Key management
   - Optional per-backup or global

4. **Incremental Backups** (Phase 3)
   - rsync-based incremental
   - Hard-link unchanged files
   - Space-efficient

5. **Verification Scheduler**
   - Periodic checksum verification
   - Alert on corruption
   - Automatic re-backup

6. **Backup Browsing**
   - View backup contents without restoring
   - Extract individual files
   - Search across backups

## References

- **Strategy**: [ADR 016: Backup Strategy](016-backups.md) (long-term vision, phases 2-3)
- **Implementation**: `packages/hop3-server/src/hop3/core/backup.py`
- **Commands**: `packages/hop3-server/src/hop3/commands/backup.py`
- **Tests**: `packages/hop3-server/tests/{a_unit,b_integration,d_e2e}/test_backup*.py`
- **User Documentation**: `docs/src/backup-restore.md`
- **Service Protocol**: `packages/hop3-server/src/hop3/core/protocols.py`

## Revision History

- **2025-11-08**: Initial ADR (v1.0)
- **2025-11-25**: Added cross-reference to ADR 016 (long-term strategy)
- Implemented in Hop3 v0.4.0
