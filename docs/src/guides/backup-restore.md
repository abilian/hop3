# Backup and Restore

Hop3 provides a comprehensive backup and restore system to protect your applications and data. This guide covers everything you need to know about backing up and restoring your Hop3 applications.

## Table of Contents

- [Overview](#overview)
- [Quick Start](#quick-start)
- [Creating Backups](#creating-backups)
- [Listing Backups](#listing-backups)
- [Viewing Backup Details](#viewing-backup-details)
- [Restoring Backups](#restoring-backups)
- [Deleting Backups](#deleting-backups)
- [Best Practices](#best-practices)
- [Troubleshooting](#troubleshooting)
- [Advanced Topics](#advanced-topics)

## Overview

### What's Included in a Backup?

Every Hop3 backup includes:

- **Source Code**: Complete git repository with all commits and history
- **Data Directory**: Application data files and user-uploaded content
- **Environment Variables**: All configuration settings and secrets
- **Attached Services**: Database dumps (PostgreSQL, etc.) and service data
- **Application Metadata**: Hostname, port, and deployment configuration

### Backup Format

Backups are stored as directories containing:

```
/var/hop3/backups/apps/<app-name>/<backup-id>/
├── metadata.json         # Backup manifest with checksums
├── source.tar.gz         # Git repository archive
├── data.tar.gz          # Application data archive
├── env.json             # Environment variables
└── services/             # Service backups
    └── postgres_<name>.sql
```

Each file is verified with **SHA256 checksums** to ensure data integrity.

### Backup IDs

Each backup has a unique ID in the format: `YYYYMMDD_HHMMSS_<random>`

Example: `20251108_143022_a8f3d9`

## Quick Start

### Create Your First Backup

```bash
# Backup an application
hop3 backup create my-app

# Output:
# Creating backup for app 'my-app'...
#
# Backup created successfully!
#
# Backup ID: 20251108_143022_a8f3d9
# Location: /var/hop3/backups/apps/my-app/20251108_143022_a8f3d9
# Total size: 15.6 MB
#
# To restore this backup:
#   hop3 backup restore 20251108_143022_a8f3d9
```

### List All Backups

```bash
hop3 backup list

# Output:
# BACKUP ID              APP         SIZE     CREATED              STATUS      SERVICES
# 20251108_143022_a8f3d9 my-app      15.6 MB  2025-11-08 14:30:22  COMPLETED   my-database
# 20251107_093015_b7e4c8 my-app      15.4 MB  2025-11-07 09:30:15  COMPLETED   my-database
```

### Restore a Backup

```bash
hop3 backup restore 20251108_143022_a8f3d9

# Output:
# Restoring backup 20251108_143022_a8f3d9...
#
# Restore completed successfully!
#
# Application: my-app
# Hostname: myapp.example.com
# Port: 8000
#
# To start the application:
#   hop3 app restart my-app
```

## Creating Backups

### Basic Backup

Create a backup of an application:

```bash
hop3 backup create <app-name>
```

**Example:**
```bash
hop3 backup create blog
```

This creates a complete backup including:
- Source code
- Data directory
- Environment variables
- All attached services (PostgreSQL, Redis, etc.)

### Backup Without Services

To create a backup excluding attached services:

```bash
hop3 backup create <app-name> --no-services
```

**Use case:** Quickly backup just the application code and data when services are backed up separately.

### What Happens During Backup?

1. **Validation**: Verifies the application exists
2. **Directory Creation**: Creates a uniquely identified backup directory
3. **Source Backup**: Archives the git repository
4. **Data Backup**: Archives the data directory
5. **Environment Backup**: Exports environment variables to JSON
6. **Service Backup**: Calls `backup()` on each attached service
7. **Checksum Generation**: Calculates SHA256 for all files
8. **Metadata Creation**: Generates `metadata.json` with inventory
9. **Database Update**: Records backup in database

The entire process is **atomic** - if any step fails, partial backups are cleaned up automatically.

## Listing Backups

### List All Backups

```bash
hop3 backup list
```

Shows all backups across all applications in a table format.

### Filter by Application

```bash
hop3 backup list <app-name>
```

**Example:**
```bash
hop3 backup list blog
```

Shows only backups for the specified application.

### Limit Results

```bash
hop3 backup list --limit <N>
```

**Example:**
```bash
hop3 backup list --limit 10
```

Shows the 10 most recent backups (default limit is 20).

### Combined Filtering

```bash
hop3 backup list blog --limit 5
```

Shows the 5 most recent backups for the "blog" application.

## Viewing Backup Details

### Get Detailed Information

```bash
hop3 backup info <backup-id>
```

**Example:**
```bash
hop3 backup info 20251108_143022_a8f3d9
```

**Output:**
```
Backup Information
==================================================

Backup ID: 20251108_143022_a8f3d9
Application: my-app
Created: 2025-11-08T14:30:22Z
Total Size: 15.6 MB
Format Version: 1.0
Hop3 Version: 0.8.0

Contents:
  - Environment: 12 variables

File Checksums:
  ✓ source.tar.gz
     sha256:abc123def456...
  ✓ data.tar.gz
     sha256:def456ghi789...
  ✓ env.json
     sha256:ghi789jkl012...

Services Included: (1)
  - postgres:my-database (8.2 MB)

Application State:
  hostname: myapp.example.com
  port: 8000
  run_state: RUNNING

Integrity: ✓ All checksums valid
```

### Verify Backup Integrity

The `backup info` command automatically verifies all checksums and reports integrity status.

## Restoring Backups

### Basic Restore

Restore an application from a backup:

```bash
hop3 backup restore <backup-id>
```

**Example:**
```bash
hop3 backup restore 20251108_143022_a8f3d9
```

### Restore to Different Application

Clone an application by restoring to a new name:

```bash
hop3 backup restore <backup-id> --target-app <new-name>
```

**Example:**
```bash
hop3 backup restore 20251108_143022_a8f3d9 --target-app blog-staging
```

This creates a completely independent copy of the application.

### What Happens During Restore?

1. **Load Metadata**: Reads and validates `metadata.json`
2. **Version Check**: Verifies Hop3 version compatibility
3. **Checksum Verification**: Validates all file checksums
4. **App Stop**: Stops the application if running
5. **Source Restore**: Extracts git repository
6. **Data Restore**: Extracts data directory
7. **Environment Restore**: Imports environment variables
8. **Service Restore**: Calls `restore()` on each service
9. **Metadata Update**: Restores hostname, port settings
10. **Database Update**: Records restore completion

The restore process includes **safety checks** at every step.

### After Restore

After restoring, you typically need to restart the application:

```bash
hop3 app restart <app-name>
```

## Deleting Backups

### Delete a Single Backup

```bash
hop3 backup destroy <backup-id>
```

**Example:**
```bash
hop3 backup destroy 20251108_143022_a8f3d9
```

**Output:**
```
Delete backup 20251108_143022_a8f3d9?

Backup details:
  Application: my-app
  Size: 15.6 MB
  Created: 2025-11-08 14:30:22

This action cannot be undone.
Type 'yes' to confirm: yes

✓ Backup deleted successfully
```

### What Gets Deleted?

- All backup files (source, data, env, services)
- Backup directory
- Database record

**Warning:** This operation is **irreversible**. Always verify the backup ID before confirming.

## Best Practices

### How Often Should I Backup?

- **Before deployments**: Always create a backup before deploying new code
- **Daily**: For production applications with frequent changes
- **Weekly**: For stable applications with infrequent updates
- **Before major changes**: Database migrations, configuration changes, etc.

### Backup Retention

Recommended retention policies:

- **Critical applications**: Keep 30+ days of daily backups
- **Standard applications**: Keep 7-14 days of backups
- **Development/staging**: Keep 3-7 days of backups

### Backup Storage

- Backups are stored in `/var/hop3/backups/`
- Monitor disk space regularly
- Consider setting up automated cleanup for old backups
- Plan for approximately 2-3x the size of your application data

### Naming Conventions

When cloning applications via restore, use clear naming:

```bash
# Good naming examples
hop3 backup restore <id> --target-app myapp-staging
hop3 backup restore <id> --target-app myapp-backup-20251108
hop3 backup restore <id> --target-app myapp-test

# Avoid ambiguous names
hop3 backup restore <id> --target-app myapp2  # Not clear what this is
```

### Testing Restores

Periodically test your backups:

1. Create a backup
2. Restore to a test application name
3. Verify the restored application works
4. Delete the test application

```bash
hop3 backup create prod-app
hop3 backup restore <backup-id> --target-app prod-app-test
hop3 app restart prod-app-test
# Test the application
hop3 app destroy prod-app-test
```

### Security Considerations

**Important:**

- Backups contain **environment variables**, which may include secrets (API keys, passwords)
- Backup files are stored with restricted permissions (600/700)
- Consider implementing backup encryption for sensitive data (future feature)
- Limit access to the hop3 server to authorized personnel only

### Backup Before:

Always create a backup before:

- Deploying new application versions
- Running database migrations
- Changing environment variables
- Modifying application configuration
- Performing system maintenance

**Quick pre-deployment checklist:**
```bash
# 1. Create backup
hop3 backup create myapp

# 2. Deploy new version
hop3 deploy myapp

# 3. If something goes wrong, restore
hop3 backup restore <backup-id>
hop3 app restart myapp
```

## Troubleshooting

### "Application not found"

**Error:**
```
Error: Application 'myapp' not found
```

**Solution:** Check the application name:
```bash
hop3 apps
```

### "Backup not found"

**Error:**
```
Error: Backup '20251108_143022_a8f3d9' not found
```

**Solution:**
```bash
# List all backups to verify the ID
hop3 backup list

# Check if you have the correct app name
hop3 backup list myapp
```

### "Checksum mismatch"

**Error:**
```
Error: Checksum mismatch for source.tar.gz
Expected: sha256:abc123...
Got: sha256:def456...
```

**Meaning:** The backup file has been corrupted or modified.

**Solution:**
- Do **not** use this backup
- Use a different backup
- Investigate how the file was corrupted
- Create a new backup from the current state

### "Insufficient disk space"

**Error:**
```
Error: Insufficient disk space for backup
```

**Solution:**
```bash
# Check disk space
df -h /var/hop3/backups

# Delete old backups
hop3 backup list
hop3 backup destroy <old-backup-id>

# Or clean up other files
```

### "Permission denied"

**Error:**
```
Error: Permission denied: /var/hop3/backups/apps/myapp/...
```

**Solution:** This usually indicates a system-level issue. Contact your system administrator or check file permissions:

```bash
ls -la /var/hop3/backups/
```

### Restore Fails Partway Through

If a restore fails:

1. **Check the error message** - it will indicate which step failed
2. **Verify the application state** - it may be partially restored
3. **Try the restore again** - some failures are transient
4. **Use a different backup** - if the issue persists

The restore process is designed to be **idempotent** - you can safely retry.

### Service Restore Fails

**Error:**
```
Error: Failed to restore service 'my-database': Connection refused
```

**Possible causes:**
- Service (PostgreSQL, Redis, etc.) is not running
- Service credentials have changed
- Service port is blocked

**Solution:**
```bash
# Check service status
hop3 postgres:list

# Restart service if needed
# Then retry restore
hop3 backup restore <backup-id>
```

## Advanced Topics

### Backup File Structure

Understanding the backup structure can help with debugging:

```
/var/hop3/backups/apps/myapp/20251108_143022_a8f3d9/
│
├── metadata.json          # Backup manifest
│   └── Contains:
│       - Backup ID and timestamps
│       - File checksums (SHA256)
│       - Service information
│       - Application metadata
│
├── source.tar.gz          # Git repository
│   └── Contains:
│       - Complete git history
│       - All branches and tags
│       - .git directory
│
├── data.tar.gz           # Application data
│   └── Contains:
│       - User uploads
│       - Application-generated files
│       - Runtime data
│
├── env.json              # Environment variables
│   └── Contains:
│       - All config set variables
│       - System-set variables
│       - Service URLs
│
└── services/             # Service backups
    └── postgres_mydb.sql # PostgreSQL dump
        - SQL dump file
        - Includes schema and data
```

### Manual Backup Verification

You can manually verify a backup:

```bash
# Navigate to backup directory
cd /var/hop3/backups/apps/myapp/20251108_143022_a8f3d9/

# View metadata
cat metadata.json | python3 -m json.tool

# Verify a checksum manually
sha256sum source.tar.gz
# Compare with metadata.json

# List contents of archives (without extracting)
tar -tzf source.tar.gz | head -20
tar -tzf data.tar.gz | head -20
```

### Service-Specific Backup Details

#### PostgreSQL Backups

PostgreSQL backups use `pg_dump`:

```sql
-- Backup format: Plain SQL
-- Can be inspected with a text editor
-- Contains:
CREATE DATABASE ...
CREATE TABLE ...
INSERT INTO ...
```

To manually inspect:
```bash
head -50 services/postgres_mydb.sql
```

#### Future Services

Redis, MySQL, and other services will follow similar patterns:
- Redis: RDB snapshot or AOF file
- MySQL: mysqldump SQL file

### Backup Performance

#### Large Applications

For applications with large data directories:

- **Expect** ~1-5 minutes per GB for backup creation
- **Compression** reduces size by 50-80% typically
- **Network** transfers not involved (all local)

#### Optimization Tips

- **Exclude temporary files**: Clean up temp files before backup
- **Data directory**: Keep only necessary files in data directory
- **Git repository**: Regular cleanup (`git gc`) reduces repo size

### Version Compatibility

Backups include the Hop3 version that created them:

- **Same version**: Fully compatible
- **Newer Hop3**: Generally compatible (backward compatible)
- **Older Hop3**: May require manual intervention

Always check compatibility warnings during restore.

### Disaster Recovery

In case of complete server failure:

1. **Install Hop3** on a new server
2. **Copy backups** from the old server (or remote storage)
3. **Restore applications** one by one:
   ```bash
   hop3 backup restore <backup-id>
   hop3 app restart <app-name>
   ```

**Pro tip:** Keep backups in multiple locations:
- Local server
- Remote backup server
- Cloud storage (future feature)

### Integration with CI/CD

Automate backups in your deployment pipeline:

```bash
#!/bin/bash
# deploy.sh

# Create backup before deployment
backup_id=$(hop3 backup create myapp | grep "Backup ID:" | awk '{print $3}')

# Deploy new version
hop3 deploy myapp

# If deployment fails, restore
if [ $? -ne 0 ]; then
    echo "Deployment failed, restoring backup..."
    hop3 backup restore $backup_id
    hop3 app restart myapp
    exit 1
fi

echo "Deployment successful! Backup ID: $backup_id"
```

### Monitoring Backup Age

Create a monitoring script:

```bash
#!/bin/bash
# check-backup-age.sh

app_name="myapp"
max_age_days=1

latest_backup=$(hop3 backup list $app_name --limit 1 | tail -n 1 | awk '{print $4}')
current_date=$(date +%s)
backup_date=$(date -d "$latest_backup" +%s)
age_seconds=$((current_date - backup_date))
age_days=$((age_seconds / 86400))

if [ $age_days -gt $max_age_days ]; then
    echo "WARNING: Last backup is $age_days days old"
    # Send alert (email, Slack, etc.)
    exit 1
fi

echo "OK: Backup is recent ($age_days days old)"
```

## Future Features

The following features are planned for future releases:

- **Automated Backups**: Schedule backups with cron-like syntax
- **Retention Policies**: Automatic cleanup of old backups
- **Backup Encryption**: Encrypt backups at rest using age or GPG
- **Remote Storage**: Push backups to S3, B2, or other remote storage
- **Incremental Backups**: Save storage with incremental snapshots
- **Backup Monitoring**: Email/webhook alerts for backup failures
- **Point-in-Time Recovery**: Restore databases to specific timestamps

## Getting Help

If you encounter issues:

1. Check this documentation
2. Review error messages carefully
3. Check [FAQ](faq.md) for common issues
4. Report bugs at [GitHub Issues](https://github.com/abilian/hop3/issues)
5. Ask in [Matrix Chat](https://matrix.to/#/#hop3:matrix.org)

## Related Guides

- [Quickstart Guide](../get-started/quickstart.md) - Getting started with Hop3
- [FAQ](faq.md) - Frequently asked questions
- [Configuration Reference](../reference/config.md) - Application configuration
- [CLI Reference](../reference/cli.md) - Complete command reference

---

**Remember:** Backups are your safety net. Test them regularly, store them securely, and never skip a backup before making changes!
