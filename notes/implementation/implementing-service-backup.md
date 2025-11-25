# Implementing Backup and Restore for Services

This guide explains how to add backup and restore functionality to Hop3 service plugins. If you're developing a new service (Redis, MySQL, MongoDB, etc.), follow these patterns to ensure it integrates properly with Hop3's backup system.

## Table of Contents

- [Overview](#overview)
- [ServiceStrategy Protocol](#servicestrategy-protocol)
- [Implementing backup()](#implementing-backup)
- [Implementing restore()](#implementing-restore)
- [Best Practices](#best-practices)
- [Testing](#testing)
- [Examples](#examples)

## Overview

Hop3's backup system automatically discovers and backs up services attached to applications. Services must implement the `ServiceStrategy` protocol, which includes `backup()` and `restore()` methods.

### How It Works

1. **Service Discovery**: The backup system finds attached services by examining environment variables (e.g., `DATABASE_URL` indicates a PostgreSQL service)
2. **Service Backup**: Calls `service.backup()` which returns a `Path` to the backup file
3. **Storage**: Copies the backup file into the backup directory structure
4. **Metadata**: Records the service backup in `metadata.json` with checksum
5. **Restoration**: During restore, calls `service.restore(backup_path)` to restore the service data

## ServiceStrategy Protocol

All services must implement the `ServiceStrategy` protocol defined in `hop3/core/protocols.py`:

```python
from pathlib import Path
from typing import Protocol

class ServiceStrategy(Protocol):
    """Protocol that all service strategies must implement."""

    # Service identification
    name: str  # e.g., "postgres", "redis", "mysql"
    service_name: str  # Instance name, e.g., "my-database"

    def create(self) -> None:
        """Create the service instance."""
        ...

    def destroy(self) -> None:
        """Destroy the service instance."""
        ...

    def backup(self) -> Path:
        """Create a backup of the service data.

        Returns:
            Path: Absolute path to the backup file
        """
        ...

    def restore(self, backup_path: Path) -> None:
        """Restore service data from a backup file.

        Args:
            backup_path: Absolute path to the backup file to restore from
        """
        ...

    def get_env_vars(self) -> dict[str, str]:
        """Get environment variables for connecting to this service.

        Returns:
            Dictionary of environment variable names and values
        """
        ...
```

## Implementing backup()

The `backup()` method should:

1. Create a backup of the service data
2. Store it in a standard location
3. Return the absolute path to the backup file

### Method Signature

```python
def backup(self) -> Path:
    """Create a backup of the service data.

    Returns:
        Path: Absolute path to the backup file

    Raises:
        RuntimeError: If backup fails
    """
```

### Implementation Pattern

```python
from datetime import datetime, timezone
from pathlib import Path
import subprocess

def backup(self) -> Path:
    """Create a backup of the PostgreSQL database using pg_dump."""
    # 1. Define backup directory
    backup_dir = Path("/var/hop3/backups") / "postgres"
    backup_dir.mkdir(parents=True, exist_ok=True)

    # 2. Generate unique filename with timestamp
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_file = backup_dir / f"{self.service_name}_{timestamp}.sql"

    # 3. Run service-specific backup command
    cmd = [
        "pg_dump",
        "-h", "localhost",
        "-U", self.db_user,
        "-d", self.db_name,
        "-f", str(backup_file),
    ]

    # 4. Execute with appropriate environment/credentials
    subprocess.run(
        cmd,
        check=True,
        env={"PGPASSWORD": self.db_password}
    )

    # 5. Return absolute path to backup file
    return backup_file
```

### Key Points

1. **Backup Directory**: Store in `/var/hop3/backups/<service-type>/`
2. **Unique Filenames**: Use timestamp + service name to avoid collisions
3. **Absolute Paths**: Always return absolute paths, not relative
4. **Error Handling**: Let exceptions propagate (BackupManager will handle them)
5. **Atomic Operations**: Ensure backup is complete before returning

## Implementing restore()

The `restore()` method should:

1. Take a backup file path as input
2. Restore the service to that state
3. Handle any necessary cleanup or preparation

### Method Signature

```python
def restore(self, backup_path: Path) -> None:
    """Restore service data from a backup file.

    Args:
        backup_path: Absolute path to the backup file

    Raises:
        FileNotFoundError: If backup file doesn't exist
        RuntimeError: If restore fails
    """
```

### Implementation Pattern

```python
from pathlib import Path
import subprocess

def restore(self, backup_path: Path) -> None:
    """Restore PostgreSQL database from a backup file."""
    # 1. Validate backup file exists
    if not backup_path.exists():
        raise FileNotFoundError(f"Backup file not found: {backup_path}")

    # 2. Prepare for restore (e.g., drop existing database if needed)
    # This depends on your service - some may need cleanup first

    # 3. Run service-specific restore command
    cmd = [
        "psql",
        "-h", "localhost",
        "-U", self.db_user,
        "-d", self.db_name,
        "-f", str(backup_path),
    ]

    # 4. Execute with appropriate environment/credentials
    subprocess.run(
        cmd,
        check=True,
        env={"PGPASSWORD": self.db_password}
    )

    # 5. No return value needed - raise exception on error
```

### Key Points

1. **Validate Input**: Check backup file exists
2. **Idempotent**: Restore should work even if run multiple times
3. **Clean State**: Consider whether you need to clear existing data first
4. **Error Handling**: Raise descriptive exceptions on failure
5. **No Return Value**: Method returns `None`, raises on error

## Best Practices

### 1. Use Service-Specific Tools

Use the official backup/restore tools for your service:

- **PostgreSQL**: `pg_dump` / `psql`
- **MySQL**: `mysqldump` / `mysql`
- **Redis**: `SAVE` / `BGSAVE` + `redis-cli`
- **MongoDB**: `mongodump` / `mongorestore`

### 2. Backup Format

Choose an appropriate format:

- **SQL databases**: Plain SQL format (human-readable, portable)
- **Key-value stores**: Native format (RDB for Redis, etc.)
- **Document databases**: JSON or BSON exports

### 3. Credentials

Handle credentials securely:

```python
# ✅ Good: Use environment variables
subprocess.run(cmd, env={"PGPASSWORD": self.db_password})

# ✅ Good: Use credential files
subprocess.run(cmd, stdin=credential_file)

# ❌ Bad: Pass credentials in command line
subprocess.run(["psql", f"--password={password}"])  # Visible in ps!
```

### 4. Filesystem Safety

```python
# ✅ Good: Create parent directories
backup_dir.mkdir(parents=True, exist_ok=True)

# ✅ Good: Use atomic operations
temp_file = backup_file.with_suffix(".tmp")
# ... write to temp_file ...
temp_file.rename(backup_file)

# ❌ Bad: Assume directory exists
backup_file.write_text(data)  # May fail if parent doesn't exist
```

### 5. Resource Cleanup

```python
def backup(self) -> Path:
    backup_file = None
    try:
        backup_file = create_backup()
        return backup_file
    except Exception:
        # Clean up partial backup on error
        if backup_file and backup_file.exists():
            backup_file.unlink()
        raise
```

### 6. Large Data Handling

For large datasets:

```python
# ✅ Good: Stream to disk
subprocess.run([
    "pg_dump", "-Fc",  # Custom format, compressed
    "-f", str(backup_file)
])

# ❌ Bad: Load into memory
data = get_all_data()  # Could be gigabytes!
backup_file.write_text(data)
```

## Testing

### Unit Tests

Test the backup/restore logic in isolation:

```python
def test_postgres_backup(tmp_path):
    """Test PostgreSQL backup creates a valid SQL file."""
    service = PostgresService(service_name="test-db")

    # Create backup
    backup_path = service.backup()

    # Verify backup file exists
    assert backup_path.exists()
    assert backup_path.suffix == ".sql"

    # Verify backup contains valid SQL
    content = backup_path.read_text()
    assert "CREATE TABLE" in content or "CREATE DATABASE" in content
```

### Integration Tests

Test with real service instances:

```python
@pytest.mark.integration
def test_postgres_backup_restore_roundtrip(postgres_container):
    """Test backup and restore preserves data."""
    service = PostgresService(service_name="test-db")

    # Populate with test data
    conn = psycopg2.connect(service.get_connection_string())
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE test (id INT, name TEXT)")
    cursor.execute("INSERT INTO test VALUES (1, 'Alice'), (2, 'Bob')")
    conn.commit()

    # Create backup
    backup_path = service.backup()

    # Drop database
    cursor.execute("DROP TABLE test")
    conn.commit()

    # Restore
    service.restore(backup_path)

    # Verify data is restored
    cursor.execute("SELECT * FROM test ORDER BY id")
    rows = cursor.fetchall()
    assert rows == [(1, 'Alice'), (2, 'Bob')]
```

### E2E Tests

Test in production-like environment with Hop3:

```python
@pytest.mark.e2e
def test_app_backup_with_postgres(deployment_target):
    """Test backing up an app with PostgreSQL service."""
    # Deploy app with database
    # Populate database
    # Create backup
    # Verify service is included in backup
    # Restore and verify data integrity
```

## Examples

### PostgreSQL (Reference Implementation)

Complete implementation from `hop3/plugins/postgresql/postgres.py`:

```python
from datetime import datetime, timezone
from pathlib import Path
import subprocess

class PostgresService:
    name: str = "postgres"
    service_name: str

    def backup(self) -> Path:
        """Create a backup using pg_dump."""
        backup_dir = Path("/var/hop3/backups") / "postgres"
        backup_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        backup_file = backup_dir / f"{self.service_name}_{timestamp}.sql"

        cmd = [
            "pg_dump",
            "-h", "localhost",
            "-U", self.db_user,
            "-d", self.db_name,
            "-f", str(backup_file),
        ]

        subprocess.run(cmd, check=True, env={"PGPASSWORD": self.db_password})
        return backup_file

    def restore(self, backup_path: Path) -> None:
        """Restore from pg_dump backup."""
        if not backup_path.exists():
            raise FileNotFoundError(f"Backup not found: {backup_path}")

        cmd = [
            "psql",
            "-h", "localhost",
            "-U", self.db_user,
            "-d", self.db_name,
            "-f", str(backup_path),
        ]

        subprocess.run(cmd, check=True, env={"PGPASSWORD": self.db_password})
```

### Redis (Example Implementation)

```python
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import shutil

class RedisService:
    name: str = "redis"
    service_name: str

    def backup(self) -> Path:
        """Create backup using Redis SAVE command and copy RDB file."""
        backup_dir = Path("/var/hop3/backups") / "redis"
        backup_dir.mkdir(parents=True, exist_ok=True)

        # Trigger Redis save
        subprocess.run(
            ["redis-cli", "-p", str(self.port), "SAVE"],
            check=True
        )

        # Copy RDB file
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        backup_file = backup_dir / f"{self.service_name}_{timestamp}.rdb"

        rdb_path = Path(f"/var/lib/redis/{self.service_name}.rdb")
        shutil.copy2(rdb_path, backup_file)

        return backup_file

    def restore(self, backup_path: Path) -> None:
        """Restore from RDB backup."""
        if not backup_path.exists():
            raise FileNotFoundError(f"Backup not found: {backup_path}")

        # Stop Redis
        subprocess.run(["redis-cli", "-p", str(self.port), "SHUTDOWN"], check=False)

        # Copy backup to Redis data directory
        rdb_path = Path(f"/var/lib/redis/{self.service_name}.rdb")
        shutil.copy2(backup_path, rdb_path)

        # Start Redis (will load RDB on startup)
        subprocess.run(["redis-server", "--port", str(self.port)], check=True)
```

### MySQL (Example Implementation)

```python
from datetime import datetime, timezone
from pathlib import Path
import subprocess

class MySQLService:
    name: str = "mysql"
    service_name: str

    def backup(self) -> Path:
        """Create backup using mysqldump."""
        backup_dir = Path("/var/hop3/backups") / "mysql"
        backup_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        backup_file = backup_dir / f"{self.service_name}_{timestamp}.sql"

        cmd = [
            "mysqldump",
            "-h", "localhost",
            "-u", self.db_user,
            f"--password={self.db_password}",
            "--single-transaction",  # Consistent snapshot
            "--routines",  # Include stored procedures
            self.db_name,
        ]

        with backup_file.open("w") as f:
            subprocess.run(cmd, stdout=f, check=True)

        return backup_file

    def restore(self, backup_path: Path) -> None:
        """Restore from mysqldump backup."""
        if not backup_path.exists():
            raise FileNotFoundError(f"Backup not found: {backup_path}")

        cmd = [
            "mysql",
            "-h", "localhost",
            "-u", self.db_user,
            f"--password={self.db_password}",
            self.db_name,
        ]

        with backup_path.open("r") as f:
            subprocess.run(cmd, stdin=f, check=True)
```

## Checklist for New Services

When implementing backup/restore for a new service:

- [ ] Implement `backup()` method returning `Path`
- [ ] Implement `restore(backup_path: Path)` method
- [ ] Use service-specific backup tools
- [ ] Store backups in `/var/hop3/backups/<service-type>/`
- [ ] Use timestamped filenames
- [ ] Handle credentials securely
- [ ] Create parent directories
- [ ] Validate backup file exists in `restore()`
- [ ] Make `restore()` idempotent
- [ ] Write unit tests
- [ ] Write integration tests with real service
- [ ] Document backup format and any special considerations
- [ ] Test with Hop3's backup system (create app, attach service, backup, restore)

## Troubleshooting

### Common Issues

**Issue**: Backup file is empty

**Cause**: Command failed silently
**Solution**: Check `subprocess.run(check=True)` and examine logs

**Issue**: Restore fails with permission denied

**Cause**: Backup file has wrong permissions
**Solution**: Ensure backup files are readable by service user

**Issue**: Service won't start after restore

**Cause**: Corrupted backup or incomplete restore
**Solution**: Verify backup integrity, check service logs

### Debugging Tips

1. **Test backup files manually**:
   ```bash
   # PostgreSQL
   psql -d mydb -f backup_file.sql

   # Redis
   redis-cli --rdb backup_file.rdb

   # MySQL
   mysql mydb < backup_file.sql
   ```

2. **Check file sizes**:
   ```python
   assert backup_file.stat().st_size > 0, "Backup file is empty!"
   ```

3. **Validate content**:
   ```python
   content = backup_file.read_text()
   assert "expected_marker" in content
   ```

## Further Reading

- [ADR 081: Backup and Restore System](../adrs/081-backup-restore-system.md)
- ServiceStrategy Protocol (in `protocols.py`)
- [Backup and Restore User Guide](../../../backup-restore.md)
- [PostgreSQL backup documentation](https://www.postgresql.org/docs/current/backup.html)
- [Redis persistence](https://redis.io/topics/persistence)
- [MySQL backup methods](https://dev.mysql.com/doc/refman/8.0/en/backup-methods.html)
