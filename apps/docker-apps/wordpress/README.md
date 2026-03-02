# WordPress on Hop3

Deploy WordPress, the world's most popular content management system, on Hop3.

## Quick Start

```bash
# Create the application
hop3 app:create wordpress

# Create and attach MySQL database
hop3 addons:create mysql wordpress-db
hop3 addons:attach wordpress wordpress-db

# Generate and set security keys
hop3 config:set wordpress \
    WORDPRESS_AUTH_KEY="$(openssl rand -base64 48)" \
    WORDPRESS_SECURE_AUTH_KEY="$(openssl rand -base64 48)" \
    WORDPRESS_LOGGED_IN_KEY="$(openssl rand -base64 48)" \
    WORDPRESS_NONCE_KEY="$(openssl rand -base64 48)" \
    WORDPRESS_AUTH_SALT="$(openssl rand -base64 48)" \
    WORDPRESS_SECURE_AUTH_SALT="$(openssl rand -base64 48)" \
    WORDPRESS_LOGGED_IN_SALT="$(openssl rand -base64 48)" \
    WORDPRESS_NONCE_SALT="$(openssl rand -base64 48)"

# Set the site URL
hop3 config:set wordpress \
    WORDPRESS_HOME="https://wordpress.example.com" \
    WORDPRESS_SITEURL="https://wordpress.example.com"

# Deploy
hop3 deploy wordpress
```

## Environment Variables

### Required (set automatically by MySQL addon)

| Variable | Description |
|----------|-------------|
| `WORDPRESS_DB_HOST` | MySQL host |
| `WORDPRESS_DB_NAME` | Database name |
| `WORDPRESS_DB_USER` | Database user |
| `WORDPRESS_DB_PASSWORD` | Database password |

### Security Keys (required for production)

| Variable | Description |
|----------|-------------|
| `WORDPRESS_AUTH_KEY` | Authentication key |
| `WORDPRESS_SECURE_AUTH_KEY` | Secure authentication key |
| `WORDPRESS_LOGGED_IN_KEY` | Logged-in key |
| `WORDPRESS_NONCE_KEY` | Nonce key |
| `WORDPRESS_AUTH_SALT` | Authentication salt |
| `WORDPRESS_SECURE_AUTH_SALT` | Secure authentication salt |
| `WORDPRESS_LOGGED_IN_SALT` | Logged-in salt |
| `WORDPRESS_NONCE_SALT` | Nonce salt |

Generate keys at: https://api.wordpress.org/secret-key/1.1/salt/

### Optional

| Variable | Default | Description |
|----------|---------|-------------|
| `WORDPRESS_HOME` | (auto) | Site home URL |
| `WORDPRESS_SITEURL` | (auto) | WordPress installation URL |
| `WORDPRESS_TABLE_PREFIX` | `wp_` | Database table prefix |
| `WP_DEBUG` | `false` | Enable debug mode |
| `WP_DEBUG_LOG` | `false` | Log debug messages |

## Features

- Automatic MySQL addon integration
- Environment-based configuration
- Reverse proxy support (HTTPS, X-Forwarded headers)
- Security hardened (file editing disabled)
- Memory optimized (256MB/512MB limits)
- Auto-updates for minor versions

## Backup

WordPress data is stored in:
- MySQL database (backed up via addon)
- `wp-content/uploads/` directory (user uploads)

```bash
# Backup
hop3 backup:create wordpress

# Restore
hop3 backup:restore wordpress <backup-id>
```

## Upgrading

WordPress handles its own updates through the admin interface. For major version upgrades:

1. Create a backup
2. Update WordPress via admin dashboard
3. Test thoroughly

## Troubleshooting

### White screen / errors

Enable debug mode:
```bash
hop3 config:set wordpress WP_DEBUG=true WP_DEBUG_LOG=true
```

Check logs:
```bash
hop3 app:logs wordpress
```

### Database connection errors

Verify database addon is attached:
```bash
hop3 config:show wordpress | grep DB
```

### Permission issues

WordPress needs write access to `wp-content/`:
```bash
hop3 run wordpress chmod -R 755 wp-content
```
