# Gitea on Hop3

Deploy Gitea, the painless self-hosted Git service, on Hop3.

## Quick Start

```bash
# Create the application
hop3 app:create gitea

# Create and attach PostgreSQL database
hop3 addons:create postgres gitea-db
hop3 addons:attach gitea gitea-db

# Generate and set security keys (required)
hop3 config:set gitea \
    GITEA__security__SECRET_KEY="$(openssl rand -hex 32)" \
    GITEA__security__INTERNAL_TOKEN="$(openssl rand -hex 64)"

# Set domain and URL
hop3 config:set gitea \
    GITEA__server__DOMAIN="gitea.example.com" \
    GITEA__server__ROOT_URL="https://gitea.example.com/"

# Set hostname
hop3 config:set gitea HOST_NAME=gitea.example.com

# Deploy
hop3 deploy gitea
```

## Environment Variables

### Database (set automatically by PostgreSQL addon)

| Variable | Description |
|----------|-------------|
| `GITEA__database__HOST` | PostgreSQL host:port |
| `GITEA__database__NAME` | Database name |
| `GITEA__database__USER` | Database user |
| `GITEA__database__PASSWD` | Database password |

### Required Settings

| Variable | Description |
|----------|-------------|
| `GITEA__security__SECRET_KEY` | Session encryption key |
| `GITEA__security__INTERNAL_TOKEN` | Internal API token |
| `GITEA__server__DOMAIN` | Your Gitea domain |
| `GITEA__server__ROOT_URL` | Full URL with trailing slash |

### Optional Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `GITEA__DEFAULT__APP_NAME` | `Gitea: Git with a cup of tea` | Instance name |
| `GITEA__server__HTTP_PORT` | `3000` | HTTP port |
| `GITEA__server__DISABLE_SSH` | `false` | Disable SSH |
| `GITEA__server__SSH_PORT` | `22` | SSH port |
| `GITEA__server__LFS_START_SERVER` | `true` | Enable Git LFS |
| `GITEA__log__LEVEL` | `Info` | Log level |

### Service Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `GITEA__service__DISABLE_REGISTRATION` | `false` | Disable user registration |
| `GITEA__service__REQUIRE_SIGNIN_VIEW` | `false` | Require login to view repos |
| `GITEA__service__REGISTER_EMAIL_CONFIRM` | `false` | Require email confirmation |

### Email Settings

| Variable | Description |
|----------|-------------|
| `GITEA__mailer__ENABLED` | Enable email (true/false) |
| `GITEA__mailer__SMTP_ADDR` | SMTP server address |
| `GITEA__mailer__SMTP_PORT` | SMTP port (default: 587) |
| `GITEA__mailer__FROM` | From email address |
| `GITEA__mailer__USER` | SMTP username |
| `GITEA__mailer__PASSWD` | SMTP password |

## Features

- Single Go binary (fast, low memory)
- Git LFS support
- Built-in CI/CD (Gitea Actions)
- Issue tracking and project boards
- Pull requests with code review
- Wiki
- Webhooks
- OAuth2 and LDAP authentication

## Post-Installation

1. Visit `https://gitea.example.com`
2. Initial setup wizard will appear
3. Create admin account
4. Start creating repositories!

## SSH Access

For SSH Git access, configure SSH port forwarding or use a separate SSH port:

```bash
# Add SSH key
hop3 run gitea ./gitea admin user generate-access-token --username admin

# Clone via SSH
git clone git@gitea.example.com:user/repo.git
```

## Git LFS

Git LFS is enabled by default. LFS objects are stored in `./data/lfs/`.

```bash
# Track large files
git lfs track "*.psd"
git add .gitattributes
git commit -m "Track PSD files with LFS"
```

## Backup

Gitea stores data in:
- PostgreSQL database (users, repos metadata, issues)
- `./repos/` directory (Git repositories)
- `./data/` directory (avatars, attachments, LFS)

```bash
# Full backup
hop3 backup:create gitea

# Restore
hop3 backup:restore gitea <backup-id>
```

### Manual Backup

```bash
# Dump Gitea data
hop3 run gitea ./gitea dump -c custom/conf/app.ini
```

## Administration

### Admin Commands

```bash
# Create admin user
hop3 run gitea ./gitea admin user create --username admin --password secret --email admin@example.com --admin

# Change user password
hop3 run gitea ./gitea admin user change-password --username admin --password newsecret

# List users
hop3 run gitea ./gitea admin user list

# Regenerate hooks
hop3 run gitea ./gitea admin regenerate hooks

# Check database consistency
hop3 run gitea ./gitea doctor check
```

## Upgrading

1. Create backup:
   ```bash
   hop3 backup:create gitea
   ```

2. Update GITEA_VERSION in hop3.toml

3. Redeploy:
   ```bash
   hop3 deploy gitea
   ```

4. Migrations run automatically on startup

## Troubleshooting

### Check Status

```bash
hop3 app:status gitea
hop3 app:logs gitea
```

### Database Connection Issues

```bash
hop3 config:show gitea | grep GITEA__database
```

### Permission Issues

```bash
hop3 run gitea chmod -R 755 repos data custom
```

### Doctor Check

```bash
hop3 run gitea ./gitea doctor check --all
```
