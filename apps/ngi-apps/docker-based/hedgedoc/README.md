# HedgeDoc on Hop3

Deploy HedgeDoc, the real-time collaborative markdown editor, on Hop3.

## Quick Start

```bash
# Create the application
hop3 app:create hedgedoc

# Create and attach PostgreSQL database
hop3 addons:create postgres hedgedoc-db
hop3 addons:attach hedgedoc hedgedoc-db

# Generate and set session secret (required)
hop3 config:set hedgedoc \
    CMD_SESSION_SECRET="$(openssl rand -hex 32)" \
    CMD_DOMAIN="hedgedoc.example.com"

# Set hostname
hop3 config:set hedgedoc HOST_NAME=hedgedoc.example.com

# Deploy
hop3 deploy hedgedoc
```

## Environment Variables

### Database (set automatically by PostgreSQL addon)

| Variable | Description |
|----------|-------------|
| `CMD_DB_URL` | PostgreSQL connection URL |

### Required Settings

| Variable | Description |
|----------|-------------|
| `CMD_SESSION_SECRET` | Session encryption secret (generate with `openssl rand -hex 32`) |
| `CMD_DOMAIN` | Your HedgeDoc domain (e.g., `hedgedoc.example.com`) |

### Optional Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `CMD_URL_ADDPORT` | `false` | Add port to URL |
| `CMD_PROTOCOL_USESSL` | `true` | Use HTTPS |
| `CMD_ALLOW_ANONYMOUS` | `true` | Allow anonymous users |
| `CMD_ALLOW_ANONYMOUS_EDITS` | `true` | Allow anonymous editing |
| `CMD_DEFAULT_PERMISSION` | `freely` | Default note permission |
| `CMD_IMAGE_UPLOAD_TYPE` | `filesystem` | Image storage type |
| `CMD_UPLOADS_PATH` | `./uploads` | Upload directory |
| `CMD_ALLOW_EMAIL_REGISTER` | `false` | Allow email registration |

### Authentication Providers

HedgeDoc supports various auth providers:

```bash
# GitHub OAuth
hop3 config:set hedgedoc \
    CMD_GITHUB_CLIENTID="your-client-id" \
    CMD_GITHUB_CLIENTSECRET="your-secret"

# Google OAuth
hop3 config:set hedgedoc \
    CMD_GOOGLE_CLIENTID="your-client-id" \
    CMD_GOOGLE_CLIENTSECRET="your-secret"

# LDAP
hop3 config:set hedgedoc \
    CMD_LDAP_URL="ldap://ldap.example.com" \
    CMD_LDAP_BINDDN="cn=admin,dc=example,dc=com" \
    CMD_LDAP_BINDCREDENTIALS="password" \
    CMD_LDAP_SEARCHBASE="ou=users,dc=example,dc=com"
```

## Features

- Real-time collaborative editing
- Markdown with extensions (math, diagrams, etc.)
- Multiple authentication options
- Revision history
- Export to various formats
- WebSocket support for live updates

## Post-Installation

1. Visit `https://hedgedoc.example.com`
2. Start creating notes!
3. Share note URLs for collaboration

## Content Storage

HedgeDoc stores:
- Notes in PostgreSQL database
- Uploaded images in `./uploads/` directory

## Backup

```bash
# Full backup (database + uploads)
hop3 backup:create hedgedoc

# Restore
hop3 backup:restore hedgedoc <backup-id>
```

## Upgrading

1. Create backup:
   ```bash
   hop3 backup:create hedgedoc
   ```

2. Update HedgeDoc version in hop3.toml

3. Redeploy:
   ```bash
   hop3 deploy hedgedoc
   ```

4. Run database migrations (automatic on startup)

## Troubleshooting

### Check Status

```bash
hop3 app:status hedgedoc
hop3 app:logs hedgedoc
```

### Database Connection Issues

Verify PostgreSQL addon:
```bash
hop3 config:show hedgedoc | grep CMD_DB_URL
```

### WebSocket Issues

HedgeDoc requires WebSocket support. Verify nginx configuration includes WebSocket headers.

### Permission Issues

```bash
hop3 run hedgedoc chmod -R 755 uploads
```
