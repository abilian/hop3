# Administrator Manual

This guide covers server administration tasks for Hop3 operators, including installation, configuration, security, monitoring, and maintenance.

## Server Requirements

### Minimum Requirements

| Resource | Minimum | Recommended |
|----------|---------|-------------|
| CPU | 1 core | 2+ cores |
| RAM | 1 GB | 4+ GB |
| Disk | 20 GB | 50+ GB SSD |
| OS | Debian 12, Ubuntu 22.04+ | Debian 12 |

### Supported Operating Systems

- **Debian** 12 (Bookworm) - Recommended
- **Ubuntu** 22.04 LTS, 24.04 LTS
- **Rocky Linux** 9
- **NixOS** (experimental)

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
# Install with optional services
sudo python3 install-server.py --with mysql,redis

# Install all optional services
sudo python3 install-server.py --with all

# Specify admin domain for web UI
sudo python3 install-server.py --admin-domain admin.example.com
```

### Post-Installation Verification

```bash
# Check system health
hop3 system:check

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
│       ├── src/               # Source code
│       ├── venv/              # Virtual environment
│       └── BUILD_ARTIFACT.json
├── repos/                     # Git repositories (bare)
│   └── myapp.git/
├── .config/                   # Configuration
│   └── hop3/
│       └── server.toml
└── logs/                      # Application logs

/var/log/hop3/                 # Server logs
/etc/nginx/sites-enabled/      # Nginx configurations
/etc/uwsgi-hop3/               # uWSGI configurations
```

---

## Configuration

### Server Configuration

**Location:** `/home/hop3/.config/hop3/server.toml`

```toml
[server]
host = "0.0.0.0"
port = 8000
debug = false

[database]
url = "sqlite:////home/hop3/.config/hop3/hop3.db"

[security]
secret_key = "your-secret-key-here"
jwt_algorithm = "HS256"
token_expiry_hours = 24

[addons.postgres]
superuser = "postgres"
superuser_password = "your-postgres-password"

[addons.mysql]
superuser = "root"
superuser_password = "your-mysql-password"

[addons.redis]
host = "localhost"
port = 6379
```

### Nginx Configuration

Hop3 automatically manages Nginx configurations. Manual changes are not recommended.

**Application configs:** `/etc/nginx/sites-enabled/<appname>.conf`
**Main config:** `/etc/nginx/nginx.conf`

To reload Nginx after manual changes:
```bash
sudo nginx -t && sudo systemctl reload nginx
```

---

## User Management

### Creating Admin Users

```bash
# Create admin user interactively
hop3 admin:create

# Create admin with specified username
hop3 admin:create --username admin

# Create with password from stdin (for scripts)
echo "password123" | hop3 admin:create --username admin --password-stdin
```

### Generating API Tokens

```bash
# Generate token for automation
hop3 admin:token --username admin

# Token with custom expiry (hours)
hop3 admin:token --username admin --expiry 168
```

### Listing Users

```bash
hop3 admin:list
```

---

## Database Addon Management

### PostgreSQL

```bash
# Create a database
hop3 addons:create postgres mydb

# List databases
hop3 addons:list --type postgres

# Get connection info
hop3 addons:info mydb

# Delete database
hop3 addons:destroy mydb
```

**Configuration:** Set `superuser_password` in `server.toml`:
```toml
[addons.postgres]
superuser = "postgres"
superuser_password = "secure-password"
```

### MySQL

```bash
# Create a database
hop3 addons:create mysql mydb

# Attach to application
hop3 addons:attach mydb --app myapp
```

**Configuration:**
```toml
[addons.mysql]
superuser = "root"
superuser_password = "secure-password"
```

### Redis

```bash
# Create Redis instance
hop3 addons:create redis mycache

# Attach to application (provides REDIS_URL)
hop3 addons:attach mycache --app myapp
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
hop3 config:set myapp HOST_NAME=myapp.example.com

# Redeploy to provision certificate
hop3 deploy myapp
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
# Comprehensive health check
hop3 system:check

# Verbose output with details
hop3 system:check --verbose
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
hop3 apps:list

# Detailed app info
hop3 apps:info myapp
```

### Log Monitoring

```bash
# View application logs
hop3 logs myapp

# Follow logs in real-time
hop3 logs myapp --follow

# View last N lines
hop3 logs myapp --lines 100

# System-wide logs
hop3 system:logs
hop3 system:logs --follow
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

### Database Backups

```bash
# Backup a database
hop3 backup:create mydb

# List backups
hop3 backup:list

# Restore from backup
hop3 backup:restore mydb --backup backup-2026-02-24.sql.gz
```

### Full Server Backup

Recommended backup targets:
```bash
# Application data
/home/hop3/apps/

# Configuration
/home/hop3/.config/hop3/

# Database files (if using SQLite)
/home/hop3/.config/hop3/hop3.db

# Git repositories
/home/hop3/repos/
```

Example backup script:
```bash
#!/bin/bash
BACKUP_DIR="/backups/hop3/$(date +%Y-%m-%d)"
mkdir -p "$BACKUP_DIR"

# Backup applications
tar -czf "$BACKUP_DIR/apps.tar.gz" /home/hop3/apps/

# Backup configuration
tar -czf "$BACKUP_DIR/config.tar.gz" /home/hop3/.config/hop3/

# Backup PostgreSQL databases
sudo -u postgres pg_dumpall | gzip > "$BACKUP_DIR/postgres.sql.gz"

# Backup MySQL databases
mysqldump --all-databases | gzip > "$BACKUP_DIR/mysql.sql.gz"
```

### Disaster Recovery

1. Install Hop3 on new server
2. Restore configuration files
3. Restore database dumps
4. Restore application directories
5. Redeploy applications: `hop3 deploy myapp`

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
hop3 config:set myapp UWSGI_WORKERS=4
hop3 config:set myapp UWSGI_THREADS=2
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

---

## Troubleshooting

### Common Issues

#### Application Won't Start

```bash
# Check application logs
hop3 logs myapp --lines 50

# Check uWSGI status
systemctl status uwsgi-hop3

# Verify environment variables
hop3 config:show myapp
```

#### 502 Bad Gateway

1. Check if application is running: `hop3 apps:list`
2. Check application logs: `hop3 logs myapp`
3. Verify Nginx config: `sudo nginx -t`
4. Check uWSGI socket: `ls -la /tmp/uwsgi-*.sock`

#### Database Connection Failed

```bash
# Verify addon is attached
hop3 addons:list

# Check DATABASE_URL is set
hop3 config:show myapp | grep DATABASE

# Test database connection
hop3 system:check --verbose
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
hop3 system:info

# Diagnostic information
hop3 system:check --verbose
```

---

## Maintenance Tasks

### Regular Maintenance Checklist

**Daily:**
- Monitor disk space: `df -h`
- Check application health: `hop3 system:check`

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
# Check current version
hop3 --version

# Update Hop3 server
pip install --upgrade hop3-server

# Restart services
sudo systemctl restart hop3-server
sudo systemctl restart uwsgi-hop3
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
| Server config | `/home/hop3/.config/hop3/server.toml` |
| Database | `/home/hop3/.config/hop3/hop3.db` |
| Applications | `/home/hop3/apps/` |
| Git repos | `/home/hop3/repos/` |
| Nginx configs | `/etc/nginx/sites-enabled/` |
| uWSGI configs | `/etc/uwsgi-hop3/` |
| Server logs | `/var/log/hop3/` |
| SSL certs | `/etc/letsencrypt/live/` |

### Environment Variables

| Variable | Description |
|----------|-------------|
| `HOP3_ROOT` | Base directory (`/home/hop3`) |
| `HOP3_CONFIG` | Config file path |
| `HOP3_UNSAFE` | Disable auth (testing only) |
| `HOP3_DEBUG` | Enable debug logging |
