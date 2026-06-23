# Administrator Manual

This guide covers server administration tasks for Hop3 operators, including installation, configuration, security, monitoring, and maintenance.

## Server Requirements

### Minimum Requirements

| Resource | Minimum | Recommended |
|----------|---------|-------------|
| CPU | 1 core | 2+ cores |
| RAM | 1 GB | 4+ GB |
| Disk | 20 GB | 50+ GB SSD |
| OS | Debian 12, Ubuntu 24.04+ | Debian 12 |

### Supported Operating Systems

- **Debian** 12 (Bookworm) - Recommended
- **Ubuntu** 24.04 LTS, 26.04 LTS
- **Rocky Linux** 9
- **NixOS** (experimental — via the Nix flake / `services.hop3` module)

On the distros above, hop3-server is installed by the standard installer; on NixOS it is deployed via the Nix flake and the `services.hop3` NixOS module. (Separately, the Nix package manager is also available as an app *builder* on any supported host.)

---

## Installation

### Quick Install (Single Command)

```bash
curl -LsSf https://hop3.cloud/install-server.py | sudo python3 -
```

### Manual Installation

```bash
# Download installer
curl -LsSf https://hop3.cloud/install-server.py -o install-server.py

# Review the script (recommended)
less install-server.py

# Run installation
sudo python3 install-server.py
```

### Installation Options

```bash
# Install with optional services (mysql, redis, docker, or all)
sudo python3 install-server.py --with mysql,redis

# Install all optional features
sudo python3 install-server.py --with all

# Specify domain for Let's Encrypt certificate
sudo python3 install-server.py --domain hop3.example.com
```

See the [Server Setup Guide](../get-started/server-setup.md) for complete installation options.

### Post-Installation Verification

```bash
# Check system health
hop3 system status

# View service status
systemctl status hop3-server
systemctl status nginx
systemctl status uwsgi-hop3
```

---

## Directory Structure

```
/home/hop3/                    # HOP3_ROOT
├── apps/                      # Application deployments
│   └── myapp/
│       ├── git/               # Bare git repository
│       ├── src/               # Checked-out source code
│       ├── data/              # Persistent data
│       ├── log/               # Log files
│       └── venv/              # Virtual environment (if applicable)
├── nginx/                     # Nginx configs and certs
├── uwsgi-available/           # uWSGI configs
├── uwsgi-enabled/             # Active uWSGI configs (symlinks)
├── backups/                   # Application backups
├── hop3-server.toml           # Server configuration
└── hop3.db                    # SQLite database
```

---

## Configuration

### Server Configuration

**Location:** `/home/hop3/hop3-server.toml`

The server reads top-level keys from this file (each key is also overridable by an environment variable of the same name). It is a flat key/value file — there are no `[section]` tables for these settings.

```toml
HOP3_SECRET_KEY = "your-secret-key-here"
HOP3_TOKEN_EXPIRY_HOURS = 24
HOP3_PROXY_TYPE = "nginx"            # nginx, caddy, or traefik
HOP3_LOG_LEVEL = "INFO"

# Addon superuser credentials
POSTGRES_SUPERUSER = "postgres"
POSTGRES_SUPERUSER_PASSWORD = "your-postgres-password"

MYSQL_SUPERUSER = "root"
MYSQL_SUPERUSER_PASSWORD = "your-mysql-password"

REDIS_HOST = "localhost"
REDIS_PORT = 6379
```

### Nginx Configuration

Hop3 automatically manages Nginx configurations. Manual changes are not recommended.

**Application configs:** `/home/hop3/nginx/<appname>.conf`
**Main config:** `/etc/nginx/nginx.conf`

To reload Nginx after manual changes:
```bash
sudo nginx -t && sudo systemctl reload nginx
```

---

## User Management

### Creating Admin Users

The recommended way to create an admin user is from your workstation:

```bash
hop3 init --ssh root@your-server.com
```

This connects via SSH, prompts for admin credentials, and saves your API token locally.

**Alternative: Server-side creation**

If you need to create users directly on the server:

```bash
ssh root@your-server.com
hop3-server admin:create admin admin@example.com
# Enter password when prompted
```

Then register the server in your local CLI (the printed token is the API token):
```bash
hop3 server add prod --url https://your-server.com --token <paste-token-here>
```

### Generating API Tokens

```bash
# Generate a token for an existing user (run on server)
hop3-server admin:token admin
```

### Listing Users

```bash
hop3 user list
```

---

## Database Addon Management

Hop3 supports PostgreSQL, MySQL, and Redis as backing services. For complete addon command documentation, see the **[CLI Reference: Services (Addons)](../reference/cli.md#services-addons)**.

### Quick Reference

```bash
hop3 addon create postgres mydb        # Create PostgreSQL database
hop3 addon create mysql mydb           # Create MySQL database
hop3 addon create redis mycache        # Create Redis instance
hop3 addon attach mydb --app myapp     # Attach to app (sets DATABASE_URL)
hop3 addon show mydb                   # Get connection info
hop3 addon destroy mydb                # Delete (requires confirmation)
```

### Server Configuration

Configure addon credentials as flat keys in `/home/hop3/hop3-server.toml`:

```toml
POSTGRES_SUPERUSER = "postgres"
POSTGRES_SUPERUSER_PASSWORD = "secure-password"

MYSQL_SUPERUSER = "root"
MYSQL_SUPERUSER_PASSWORD = "secure-password"

REDIS_HOST = "localhost"
REDIS_PORT = 6379
```

---

## SSL/TLS Certificates

### Automatic Certificates (Let's Encrypt)

Hop3 automatically provisions SSL certificates via Let's Encrypt when:

1. Application has `HOST_NAME` configured
2. Domain DNS points to server IP
3. Port 80 is accessible for ACME challenge

```bash
# Configure hostname
hop3 config set --app myapp HOST_NAME=myapp.example.com

# Redeploy to provision certificate
hop3 deploy --app myapp
```

### Manual Certificate Installation

```bash
# Copy certificates to standard location
sudo cp fullchain.pem /etc/ssl/certs/myapp.example.com.crt
sudo cp privkey.pem /etc/ssl/private/myapp.example.com.key

# Set permissions
sudo chmod 644 /etc/ssl/certs/myapp.example.com.crt
sudo chmod 600 /etc/ssl/private/myapp.example.com.key
```

### Certificate Renewal

Let's Encrypt certificates auto-renew via systemd timer:
```bash
# Check timer status
systemctl status certbot.timer

# Manual renewal test
sudo certbot renew --dry-run
```

---

## Monitoring & Health Checks

### System Health Check

```bash
# Comprehensive health report (services, addons, disk, certs)
hop3 system status

# One-line summary, suitable for scripting
hop3 system status --quiet
```

Checks performed:
- Core services (hop3-server, nginx, uwsgi)
- Database addons (PostgreSQL, MySQL, Redis)
- Filesystem permissions
- Disk space
- SSL certificates

### Application Status

```bash
# List all applications with status
hop3 apps

# Detailed app info
hop3 app status --app myapp
```

### Log Monitoring

```bash
# View application logs
hop3 app logs --app myapp

# View last N lines
hop3 app logs --app myapp --lines 100

# Filter to lines matching a pattern
hop3 app logs --app myapp --grep error

# Only the logs since the last deployment
hop3 app logs --app myapp --since-deploy

# System-wide logs
hop3 system logs
hop3 system logs --lines 100
```

### Process Monitoring

```bash
# Check uWSGI processes
systemctl status uwsgi-hop3

# View all app workers
ps aux | grep uwsgi
```

---

## Backup & Restore

For application-level backups, see the **[Backup and Restore Guide](backup-restore.md)**.

### Application Backups

```bash
hop3 backup create --app myapp   # Create app backup
hop3 backup list myapp           # List backups for an app
hop3 backup restore <id>         # Restore from backup
```

### Full Server Backup

For disaster recovery, backup these directories:

| Path | Contents |
|------|----------|
| `/home/hop3/apps/` | Application deployments (source, venv, and bare git repo) |
| `/home/hop3/hop3-server.toml` | Server configuration |
| `/home/hop3/hop3.db` | SQLite database |

Example server backup script:
```bash
#!/bin/bash
BACKUP_DIR="/backups/hop3/$(date +%Y-%m-%d)"
mkdir -p "$BACKUP_DIR"

tar -czf "$BACKUP_DIR/apps.tar.gz" /home/hop3/apps/
cp /home/hop3/hop3-server.toml /home/hop3/hop3.db "$BACKUP_DIR/"
sudo -u postgres pg_dumpall | gzip > "$BACKUP_DIR/postgres.sql.gz"
```

### Disaster Recovery

1. Install Hop3 on new server
2. Restore configuration and database files
3. Restore application directories
4. Redeploy applications: `hop3 deploy --app myapp`

---

## Security Hardening

### Firewall Configuration

```bash
# Allow SSH
sudo ufw allow 22/tcp

# Allow HTTP/HTTPS
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp

# Enable firewall
sudo ufw enable
```

### SSH Hardening

Edit `/etc/ssh/sshd_config`:
```
PermitRootLogin no
PasswordAuthentication no
PubkeyAuthentication yes
```

Reload SSH:
```bash
sudo systemctl reload sshd
```

### Database Security

**PostgreSQL** - Edit `/etc/postgresql/*/main/pg_hba.conf`:
```
# Local connections
local   all   all                 peer
# Docker bridge network
host    all   all   172.16.0.0/12   md5
# Docker Compose networks
host    all   all   192.168.0.0/16  md5
```

**MySQL** - Ensure strong root password:
```bash
sudo mysql_secure_installation
```

### Application Isolation

Each application runs:
- In isolated directory (`/home/hop3/apps/<name>/`)
- With dedicated virtual environment
- Under the `hop3` user
- With separate uWSGI worker processes

---

## Performance Tuning

### uWSGI Workers

Edit application's uWSGI config or set via environment:
```bash
hop3 config set --app myapp UWSGI_WORKERS=4
hop3 config set --app myapp UWSGI_THREADS=2
```

### Nginx Optimization

```nginx
# /etc/nginx/nginx.conf
worker_processes auto;
worker_connections 1024;

# Enable gzip
gzip on;
gzip_types text/plain application/json application/javascript text/css;

# Enable caching
proxy_cache_path /var/cache/nginx levels=1:2 keys_zone=cache:10m;
```

### Database Tuning

**PostgreSQL** - Edit `/etc/postgresql/*/main/postgresql.conf`:
```
shared_buffers = 256MB
effective_cache_size = 1GB
maintenance_work_mem = 64MB
```

### Docker Network Configuration

When running many Docker-based applications (20+), you may encounter the error:

```
failed to create network: all predefined address pools have been fully subnetted
```

**Cause:** Docker's default configuration allocates /16 subnets for bridge networks, limiting you to approximately 16 networks from the default 172.17.0.0/12 pool.

**Solution:** Configure Docker to use smaller /24 subnets, allowing up to 4096 networks:

```bash
# Create or edit /etc/docker/daemon.json
sudo tee /etc/docker/daemon.json << EOF
{
  "default-address-pools": [
    {"base": "172.17.0.0/12", "size": 24}
  ]
}
EOF

# Restart Docker to apply changes
sudo systemctl restart docker
```

**Note:** Restarting Docker will stop all running containers. They will need to be restarted or redeployed.

**Important:** After changing Docker's network configuration, you must also update PostgreSQL to listen on the new network range:

```bash
# Update PostgreSQL to listen on all interfaces
sudo sed -i "s/listen_addresses = .*/listen_addresses = '*'/" /etc/postgresql/*/main/postgresql.conf

# Update pg_hba.conf to allow connections from Docker networks
# Add this line if not present:
echo "host    all    all    172.16.0.0/12    scram-sha-256" | sudo tee -a /etc/postgresql/*/main/pg_hba.conf

# Restart PostgreSQL
sudo systemctl restart postgresql
```

**Verification:**
```bash
# Check current networks
docker network ls

# After deploying many apps, verify no pool exhaustion
docker network create test-network && docker network rm test-network
```

---

## Troubleshooting

### Common Issues

#### Application Won't Start

```bash
# Check application logs
hop3 app logs --app myapp --lines 50

# Check uWSGI status
systemctl status uwsgi-hop3

# Verify environment variables
hop3 config show --app myapp
```

#### 502 Bad Gateway

1. Check if application is running: `hop3 apps`
2. Check application logs: `hop3 app logs --app myapp`
3. Verify Nginx config: `sudo nginx -t`
4. Check uWSGI socket: `ls -la /tmp/uwsgi-*.sock`

#### Database Connection Failed

```bash
# Verify addon is attached
hop3 addon list

# Check DATABASE_URL is set
hop3 config show --app myapp | grep DATABASE

# Re-check server health (services and addons)
hop3 system status
```

#### SSL Certificate Issues

```bash
# Check certificate status
sudo certbot certificates

# Force renewal
sudo certbot renew --force-renewal

# Check Nginx SSL config
sudo nginx -t
```

### Getting Help

```bash
# Built-in help
hop3 --help
hop3 <command> --help

# System information
hop3 system info

# Health report with diagnostics
hop3 system status
```

---

## Maintenance Tasks

### Regular Maintenance Checklist

**Daily:**
- Monitor disk space: `df -h`
- Check server health: `hop3 system status`

**Weekly:**
- Review logs for errors
- Verify backups are running
- Check certificate expiry: `sudo certbot certificates`

**Monthly:**
- Update system packages: `sudo apt update && sudo apt upgrade`
- Review and rotate logs
- Test backup restoration
- Review security logs

### Updating Hop3

```bash
# Check the running server version
hop3 system info

# Update Hop3 server by re-running the installer (idempotent: it preserves
# operator config and secrets, and restarts the services)
curl -LsSf https://hop3.cloud/install-server.py | sudo python3 -
```

### Log Rotation

Hop3 logs are managed by systemd journal. Configure retention:
```bash
# Edit /etc/systemd/journald.conf
SystemMaxUse=500M
MaxRetentionSec=30day
```

Apply changes:
```bash
sudo systemctl restart systemd-journald
```

---

## Reference

### Service Management

| Service | Command |
|---------|---------|
| Hop3 Server | `systemctl {start,stop,restart,status} hop3-server` |
| Nginx | `systemctl {start,stop,restart,status} nginx` |
| uWSGI | `systemctl {start,stop,restart,status} uwsgi-hop3` |
| PostgreSQL | `systemctl {start,stop,restart,status} postgresql` |
| MySQL | `systemctl {start,stop,restart,status} mysql` |
| Redis | `systemctl {start,stop,restart,status} redis-server` |

### Important File Locations

| Purpose | Location |
|---------|----------|
| Server config | `/home/hop3/hop3-server.toml` |
| Database | `/home/hop3/hop3.db` |
| Applications | `/home/hop3/apps/` |
| Git repos | `/home/hop3/apps/<name>/git/` |
| Nginx configs | `/home/hop3/nginx/` |
| uWSGI configs | `/home/hop3/uwsgi-available/`, `/home/hop3/uwsgi-enabled/` |
| Application logs | `/home/hop3/apps/<name>/log/` |
| SSL certs | `/etc/letsencrypt/live/` |

### Environment Variables

| Variable | Description |
|----------|-------------|
| `HOP3_ROOT` | Base directory (`/home/hop3`); the config file is `$HOP3_ROOT/hop3-server.toml` |
| `HOP3_LOG_LEVEL` | Server log level (default: `INFO`) |
| `HOP3_UNSAFE` | Disable auth (testing only) |
| `HOP3_DEBUG` | Enable debug logging |

---

## Related Guides

- **[Server Setup](../get-started/server-setup.md)** - Initial server installation
- **[User Guide](user-guide.md)** - Core concepts and daily operations
- **[Backup and Restore](backup-restore.md)** - Data protection and recovery
- **[Troubleshooting](troubleshooting.md)** - Diagnose and fix common issues
- **[CLI Reference](../reference/cli.md)** - Complete command documentation
