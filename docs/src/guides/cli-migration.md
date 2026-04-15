# CLI Migration Guide: Updating Scripts for New CLI

This guide helps you update existing automation scripts and workflows to work with Hop3's enhanced CLI interface introduced in Step 2.4.

## Overview of Changes

The Hop3 CLI has been enhanced with:

- **Rich formatted output** - Tables, colors, and panels for better readability
- **JSON output mode** - Machine-readable output for automation (`--json`)
- **Quiet mode** - Minimal output for scripts (`--quiet`)
- **Confirmation prompts** - Type-to-confirm for destructive operations
- **Skip confirmations** - `-y` flag to bypass prompts in automation
- **Consistent command naming** - Some commands have been renamed for clarity

**Good news:** The core functionality remains the same. Most scripts will continue to work without changes. However, we recommend updating them to take advantage of new features.

---

## Breaking Changes

### 1. Destructive Commands Now Require Confirmation

**Affected commands:**
- `hop3 app destroy <app>`
- `hop3 backup destroy <backup-id>`
- `hop3 addon destroy <service>`

**What changed:**
These commands now prompt for confirmation by typing the app/service name or backup ID.

**Migration:**

**Before:**
```bash
#!/bin/bash
hop3 app destroy old-app
hop3 backup destroy old-backup-123
```

**After (Option 1 - Add -y flag):**
```bash
#!/bin/bash
hop3 app destroy old-app -y
hop3 backup destroy old-backup-123 -y
```

**After (Option 2 - Use expect for interactive confirmation):**
```bash
#!/bin/bash
expect << EOF
spawn hop3 app destroy old-app
expect "Type the app name to confirm:"
send "old-app\r"
expect eof
EOF
```

**Recommendation:** Use the `-y` flag for automation, but ensure your scripts have proper safeguards to prevent accidental deletions.

---

## Recommended Updates

### 2. Use JSON Output for Parsing

**Why:** Rich formatted output (tables, colors) is great for humans but difficult to parse in scripts. Use `--json` for machine-readable output.

**Migration:**

**Before (parsing text output):**
```bash
#!/bin/bash
# Fragile - breaks if output format changes
STATUS=$(hop3 app status myapp | grep "Status:" | awk '{print $2}')
if [ "$STATUS" = "RUNNING" ]; then
    echo "App is running"
fi
```

**After (parsing JSON):**
```bash
#!/bin/bash
# Robust - works with any output format changes
STATUS=$(hop3 app status myapp --json | jq -r '.data.state')
if [ "$STATUS" = "RUNNING" ]; then
    echo "App is running"
fi
```

**Benefits:**
- Stable API (JSON structure won't change)
- Easy parsing with `jq`
- No dependency on output formatting

### 3. Use Quiet Mode for Clean Output

**Why:** Rich output includes progress messages, colors, and formatting that can clutter logs. Use `--quiet` to suppress non-essential output.

**Migration:**

**Before:**
```bash
#!/bin/bash
hop3 deploy
# Output:
# ╭─────────────────────────────────╮
# │    Deploying Application        │
# ╰─────────────────────────────────╯
# ✓ Uploaded code
# ✓ Built application
# ✓ Started processes
# Deployment successful!
```

**After:**
```bash
#!/bin/bash
hop3 deploy --quiet
# Output (only errors or critical info):
# Deployment successful!
```

**Best practice:** Combine `--json` and `--quiet` for clean, parseable output:
```bash
#!/bin/bash
RESULT=$(hop3 deploy --json --quiet)
if [ $? -eq 0 ]; then
    echo "Deploy succeeded"
    echo "$RESULT" | jq -r '.data.url'
else
    echo "Deploy failed"
    echo "$RESULT" | jq -r '.error.message'
fi
```

---

## Command Reference Updates

### 4. Command Naming Changes

Some commands have been renamed for consistency and clarity.

| Old Command | New Command | Notes |
|------------|-------------|-------|
| `hop3 destroy <app>` | `hop3 app destroy <app>` | Namespaced under `app:` |
| `hop3 status <app>` | `hop3 app status <app>` | Namespaced under `app:` |
| `hop3 restart <app>` | `hop3 app restart <app>` | Namespaced under `app:` |

**Migration:**

**Before:**
```bash
hop3 status myapp
hop3 restart myapp
hop3 destroy myapp
```

**After:**
```bash
hop3 app status myapp
hop3 app restart myapp
hop3 app destroy myapp
```

**Note:** Old commands may still work as aliases, but we recommend updating to the new names for future compatibility.

---

## Complete Migration Examples

### Example 1: Deployment Script

**Before:**
```bash
#!/bin/bash
set -e

echo "Deploying application..."
hop3 deploy

echo "Checking status..."
hop3 status myapp | grep "RUNNING"

echo "Deployment complete!"
```

**After:**
```bash
#!/bin/bash
set -e

echo "Deploying application..."
hop3 deploy --quiet

echo "Checking status..."
STATUS=$(hop3 app status myapp --json --quiet | jq -r '.data.state')

if [ "$STATUS" = "RUNNING" ]; then
    echo "Deployment complete! App is running."
    exit 0
else
    echo "Deployment failed. App status: $STATUS"
    exit 1
fi
```

### Example 2: Backup and Cleanup Script

**Before:**
```bash
#!/bin/bash

# Create backup
hop3 backup create myapp

# Deploy new version
hop3 deploy

# Delete old backups (keep last 5)
BACKUPS=$(hop3 backup list myapp | tail -n +6)
for backup in $BACKUPS; do
    hop3 backup destroy "$backup"
done
```

**After:**
```bash
#!/bin/bash
set -e

# Create backup and capture ID
echo "Creating backup..."
BACKUP_RESPONSE=$(hop3 backup create myapp --json --quiet)
BACKUP_ID=$(echo "$BACKUP_RESPONSE" | jq -r '.data.backup_id')
echo "Backup created: $BACKUP_ID"

# Deploy new version
echo "Deploying..."
hop3 deploy --quiet

# Test deployment
STATUS=$(hop3 app status myapp --json --quiet | jq -r '.data.state')
if [ "$STATUS" != "RUNNING" ]; then
    echo "Deployment failed! Rolling back..."
    hop3 backup restore "$BACKUP_ID" -y
    hop3 app restart myapp -y
    exit 1
fi

# Delete old backups (keep last 5)
echo "Cleaning up old backups..."
OLD_BACKUPS=$(hop3 backup list myapp --json --quiet | \
    jq -r '.data | sort_by(.created) | reverse | .[5:] | .[].id')

for backup_id in $OLD_BACKUPS; do
    echo "Deleting backup: $backup_id"
    hop3 backup destroy "$backup_id" -y
done

echo "Deployment and cleanup complete!"
```

### Example 3: Health Check Script

**Before:**
```bash
#!/bin/bash

for app in app1 app2 app3; do
    echo "Checking $app..."
    hop3 status "$app"
done
```

**After:**
```bash
#!/bin/bash

echo "Application Health Check"
echo "========================"

FAILED=0

for app in app1 app2 app3; do
    STATUS=$(hop3 app status "$app" --json --quiet 2>/dev/null | jq -r '.data.state')

    if [ "$STATUS" = "RUNNING" ]; then
        echo "✓ $app: RUNNING"
    else
        echo "✗ $app: $STATUS"
        FAILED=$((FAILED + 1))
    fi
done

echo ""
if [ $FAILED -eq 0 ]; then
    echo "All applications healthy!"
    exit 0
else
    echo "$FAILED application(s) not running"
    exit 1
fi
```

### Example 4: Environment Variable Management

**Before:**
```bash
#!/bin/bash

# Set variables
hop3 config set myapp DATABASE_URL=postgres://...
hop3 config set myapp REDIS_URL=redis://...
hop3 config set myapp SECRET_KEY=abc123

# Restart
hop3 restart myapp
```

**After:**
```bash
#!/bin/bash
set -e

# Set multiple variables in one command
echo "Setting environment variables..."
hop3 config set myapp \
    DATABASE_URL=postgres://... \
    REDIS_URL=redis://... \
    SECRET_KEY=abc123 \
    --quiet

# Verify variables are set
echo "Verifying configuration..."
VARS=$(hop3 config show myapp --json --quiet | jq -r '.data | keys[]')
echo "Set variables: $VARS"

# Restart application
echo "Restarting application..."
hop3 app restart myapp --quiet

# Verify restart
STATUS=$(hop3 app status myapp --json --quiet | jq -r '.data.state')
if [ "$STATUS" = "RUNNING" ]; then
    echo "Configuration updated and app restarted successfully!"
else
    echo "Error: App failed to start after configuration change"
    exit 1
fi
```

---

## Testing Your Migrated Scripts

### 1. Test in a Safe Environment

Always test migrated scripts in a development or staging environment first:

```bash
# Set HOP3_DEV_HOST to target a test server
export HOP3_DEV_HOST=dev.hop3.example.com
hop3 login --server $HOP3_DEV_HOST

# Run your migrated script
./deploy.sh
```

### 2. Verify JSON Output Structure

Check that your JSON parsing is correct:

```bash
# See the full JSON structure
hop3 app status myapp --json | jq .

# Test your jq queries
hop3 app status myapp --json | jq -r '.data.state'
hop3 backup list myapp --json | jq -r '.data[].id'
```

### 3. Test Error Handling

Ensure your scripts handle errors gracefully:

```bash
# Test with non-existent app
hop3 app status fake-app --json --quiet
echo "Exit code: $?"

# Test destructive command with -y
hop3 app destroy test-app -y
```

---

## Common Patterns

### Pattern 1: Retry Logic

```bash
#!/bin/bash

MAX_RETRIES=3
RETRY_DELAY=5

for i in $(seq 1 $MAX_RETRIES); do
    echo "Attempt $i of $MAX_RETRIES..."

    if hop3 deploy --quiet; then
        echo "Deploy succeeded"
        exit 0
    fi

    if [ $i -lt $MAX_RETRIES ]; then
        echo "Deploy failed, retrying in ${RETRY_DELAY}s..."
        sleep $RETRY_DELAY
    fi
done

echo "Deploy failed after $MAX_RETRIES attempts"
exit 1
```

### Pattern 2: Waiting for App to Start

```bash
#!/bin/bash

echo "Waiting for app to start..."
for i in {1..30}; do
    STATUS=$(hop3 app status myapp --json --quiet | jq -r '.data.state')

    if [ "$STATUS" = "RUNNING" ]; then
        echo "App is running!"
        exit 0
    fi

    echo "Status: $STATUS (attempt $i/30)"
    sleep 2
done

echo "Timeout waiting for app to start"
exit 1
```

### Pattern 3: Conditional Deployment

```bash
#!/bin/bash

# Only deploy if app is currently running
CURRENT_STATUS=$(hop3 app status myapp --json --quiet | jq -r '.data.state')

if [ "$CURRENT_STATUS" != "RUNNING" ]; then
    echo "App is not running. Start it first with: hop3 app start myapp"
    exit 1
fi

# Create backup before deploy
echo "Creating pre-deployment backup..."
BACKUP_ID=$(hop3 backup create myapp --json --quiet | jq -r '.data.backup_id')

# Deploy
if hop3 deploy --quiet; then
    echo "Deploy succeeded"
else
    echo "Deploy failed! Restoring from backup $BACKUP_ID"
    hop3 backup restore "$BACKUP_ID" -y
    hop3 app restart myapp -y
    exit 1
fi
```

---

## Frequently Asked Questions

### Q: Will my old scripts break?

**A:** Most scripts will continue to work. The main breaking change is that destructive commands now require confirmation. Add the `-y` flag to skip confirmations.

### Q: Do I need to migrate to JSON output?

**A:** No, but it's highly recommended. JSON output is stable and easier to parse. Text output may change in future versions.

### Q: Can I still use colored output in CI/CD?

**A:** Colors are automatically disabled when output is not a TTY (like in CI/CD). To force colors on or off, use:
```bash
# Force colors on
export FORCE_COLOR=1

# Force colors off
export NO_COLOR=1
```

### Q: What if I need to parse output without jq?

**A:** Install `jq` - it's the best tool for JSON parsing. Alternatively, use Python:
```bash
hop3 app status myapp --json | python3 -c "import sys, json; print(json.load(sys.stdin)['data']['state'])"
```

### Q: How do I debug script issues?

**A:** Use verbose mode to see detailed output:
```bash
hop3 deploy -v --json
```

---

## Migration Checklist

Use this checklist to ensure your scripts are fully migrated:

- [ ] Add `-y` flag to all destructive commands (`app destroy`, `backup destroy`, etc.)
- [ ] Replace text output parsing with `--json` + `jq`
- [ ] Add `--quiet` to commands in scripts for clean output
- [ ] Update old command names to namespaced versions (`status` → `app status`)
- [ ] Add error handling for failed commands
- [ ] Test scripts in development environment
- [ ] Verify JSON parsing with sample data
- [ ] Add `set -e` to scripts to exit on first error
- [ ] Document any `-y` usage with comments about safety

---

## Getting Help

If you encounter issues migrating your scripts:

1. **Check the CLI Reference**: See [CLI Reference](../reference/cli.md) for complete command documentation
2. **Test with --json**: Always test JSON output structure with `| jq .`
3. **Use --verbose**: Debug issues with verbose output
4. **Check exit codes**: All commands return proper exit codes (0 = success, non-zero = error)

For more help:
```bash
hop3 help
hop3 <command> --help
```

---

## Summary

**Key takeaways:**

1. **Add `-y` to destructive commands** in automation scripts
2. **Use `--json`** for parsing output in scripts
3. **Use `--quiet`** to minimize output noise
4. **Update command names** to namespaced versions
5. **Always test** in development before production

The new CLI provides better error handling, cleaner output, and more robust automation capabilities. Taking the time to migrate your scripts will make them more maintainable and reliable.
