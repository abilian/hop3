# Nextcloud on Hop3

Deploy Nextcloud, the self-hosted file sync and collaboration platform, on Hop3.

## Quick Start

```bash
# Create the application
hop3 app:create nextcloud

# Create and attach PostgreSQL database
hop3 addons:create postgres nextcloud-db
hop3 addons:attach nextcloud nextcloud-db

# Create and attach Redis cache (recommended)
hop3 addons:create redis nextcloud-cache
hop3 addons:attach nextcloud nextcloud-cache

# Set admin password and trusted domain
hop3 config:set nextcloud \
    NEXTCLOUD_ADMIN_PASSWORD="$(openssl rand -base64 24)" \
    NEXTCLOUD_TRUSTED_DOMAINS="nextcloud.example.com" \
    NEXTCLOUD_URL="https://nextcloud.example.com"

# Set hostname
hop3 config:set nextcloud HOST_NAME=nextcloud.example.com

# Deploy
hop3 deploy nextcloud
```

## Environment Variables

### Database (set automatically by PostgreSQL addon)

| Variable | Description |
|----------|-------------|
| `POSTGRES_HOST` | PostgreSQL host |
| `POSTGRES_DB` | Database name |
| `POSTGRES_USER` | Database user |
| `POSTGRES_PASSWORD` | Database password |

### Redis (set automatically by Redis addon)

| Variable | Description |
|----------|-------------|
| `REDIS_HOST` | Redis host |
| `REDIS_PORT` | Redis port (default: 6379) |
| `REDIS_PASSWORD` | Redis password (if set) |

### Nextcloud Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `NEXTCLOUD_ADMIN_USER` | `admin` | Admin username |
| `NEXTCLOUD_ADMIN_PASSWORD` | (required) | Admin password |
| `NEXTCLOUD_TRUSTED_DOMAINS` | | Comma-separated list of trusted domains |
| `NEXTCLOUD_URL` | | Full URL for CLI operations |
| `NEXTCLOUD_DATA_DIR` | `./data` | Data storage directory |
| `OVERWRITEPROTOCOL` | `https` | Protocol for URL generation |
| `NEXTCLOUD_LOGLEVEL` | `2` | Log level (0=debug, 4=fatal) |

### Email (optional)

| Variable | Description |
|----------|-------------|
| `SMTP_HOST` | SMTP server hostname |
| `SMTP_PORT` | SMTP port (default: 587) |
| `SMTP_SECURE` | Security mode (tls, ssl) |
| `SMTP_USER` | SMTP username |
| `SMTP_PASSWORD` | SMTP password |
| `MAIL_FROM_ADDRESS` | From address (local part) |
| `MAIL_DOMAIN` | From address domain |

## Features

- Automatic PostgreSQL integration
- Redis caching for improved performance
- Background job support (cron)
- Reverse proxy optimized (HTTPS, trusted proxies)
- Security headers configured
- Large file upload support (16GB)
- APCu local caching

## Post-Installation

After first deployment, complete the setup:

1. Visit `https://nextcloud.example.com`
2. The installer will run automatically with your configured settings
3. Install recommended apps via the admin panel

### Configure Additional Settings

```bash
# Run Nextcloud CLI commands
hop3 run nextcloud php occ status
hop3 run nextcloud php occ app:list
hop3 run nextcloud php occ maintenance:mode --on
```

## Backup

Nextcloud data includes:
- PostgreSQL database
- Data directory (`./data/`)
- Config files (`./config/`)

```bash
# Full backup
hop3 backup:create nextcloud

# Restore
hop3 backup:restore nextcloud <backup-id>
```

## Upgrading

1. Enable maintenance mode:
   ```bash
   hop3 run nextcloud php occ maintenance:mode --on
   ```

2. Create backup:
   ```bash
   hop3 backup:create nextcloud
   ```

3. Update Nextcloud version in hop3.toml and redeploy

4. Run upgrade:
   ```bash
   hop3 run nextcloud php occ upgrade
   ```

5. Disable maintenance mode:
   ```bash
   hop3 run nextcloud php occ maintenance:mode --off
   ```

## Troubleshooting

### Permission Issues

```bash
hop3 run nextcloud php occ maintenance:repair
```

### Database Issues

```bash
hop3 run nextcloud php occ db:add-missing-indices
hop3 run nextcloud php occ db:convert-filecache-bigint
```

### Check System Status

```bash
hop3 run nextcloud php occ status
hop3 run nextcloud php occ check
```

### View Logs

```bash
hop3 app:logs nextcloud
hop3 run nextcloud cat data/nextcloud.log | tail -50
```
