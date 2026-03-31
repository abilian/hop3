# Ghost on Hop3

Deploy Ghost, the professional publishing platform, on Hop3.

## Quick Start

```bash
# Create the application
hop3 app:create ghost

# Create and attach MySQL database
hop3 addons:create mysql ghost-db
hop3 addons:attach ghost ghost-db

# Set the site URL (required)
hop3 config:set ghost \
    GHOST_URL="https://ghost.example.com"

# Set hostname
hop3 config:set ghost HOST_NAME=ghost.example.com

# Deploy
hop3 deploy ghost
```

## Environment Variables

### Database (set automatically by MySQL addon)

| Variable | Description |
|----------|-------------|
| `database__connection__host` | MySQL host |
| `database__connection__database` | Database name |
| `database__connection__user` | Database user |
| `database__connection__password` | Database password |

### Required Settings

| Variable | Description |
|----------|-------------|
| `GHOST_URL` | Full URL of your Ghost site (e.g., `https://ghost.example.com`) |

### Optional Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | `2368` | HTTP port |
| `GHOST_LOG_LEVEL` | `info` | Logging level |
| `GHOST_CONTENT_PATH` | `./content` | Content storage path |

### Email Settings

| Variable | Description |
|----------|-------------|
| `mail__transport` | Mail transport (SMTP, Mailgun, etc.) |
| `mail__options__host` | SMTP host |
| `mail__options__port` | SMTP port (default: 587) |
| `mail__options__secure` | Use TLS (true/false) |
| `mail__options__auth__user` | SMTP username |
| `mail__options__auth__pass` | SMTP password |

## Features

- Automatic MySQL integration
- Production-optimized Node.js configuration
- Reverse proxy support
- Content stored in `./content/` directory
- Automatic database migrations

## Post-Installation

1. Visit `https://ghost.example.com/ghost` to create your admin account
2. Configure your publication settings
3. Start writing!

## Content Management

Ghost stores content in:
- MySQL database (posts, users, settings)
- `./content/` directory (themes, images, files)

### Themes

Upload themes via the Ghost admin panel or:

```bash
# Copy theme to content/themes/
hop3 run ghost cp -r /path/to/theme content/themes/

# Restart to pick up new theme
hop3 app:restart ghost
```

## Backup

```bash
# Full backup (database + content)
hop3 backup:create ghost

# Restore
hop3 backup:restore ghost <backup-id>
```

## Upgrading

Ghost handles updates through its admin panel for minor versions. For major upgrades:

1. Create backup:
   ```bash
   hop3 backup:create ghost
   ```

2. Update Ghost version in your deployment

3. Run migrations:
   ```bash
   hop3 run ghost "cd current && NODE_ENV=production node index.js --migrate"
   ```

## Troubleshooting

### Check Ghost Status

```bash
hop3 app:status ghost
hop3 app:logs ghost
```

### Database Connection Issues

Verify MySQL addon is attached:
```bash
hop3 config:show ghost | grep database
```

### Reset Admin Password

```bash
hop3 run ghost "cd current && node index.js --reset-password"
```

### Clear Cache

```bash
hop3 run ghost "rm -rf content/cache/*"
hop3 app:restart ghost
```
