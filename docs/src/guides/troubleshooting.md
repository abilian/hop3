# Troubleshooting Guide

This guide helps you diagnose and fix common issues with Hop3 deployments.

## Quick Diagnostics

Before diving into specific issues, run these commands to gather information:

```bash
# System health check
hop3 system status

# Application status
hop3 app list

# Recent logs
hop3 app logs --app myapp --lines 50

# System info
hop3 system info
```

## Deployment Issues

### Build Fails

#### Symptom
Deployment fails during the build phase with dependency or compilation errors.

#### Diagnosis
```bash
hop3 app logs --app myapp --lines 100
```

#### Common Causes & Solutions

**Missing system dependencies:**
```bash
# Check if required packages are installed
dpkg -l | grep <package>

# Install missing packages
sudo apt install <package>
```

**Python: pip install fails**
```bash
# Check Python version
python3 --version

# Ensure pip is up to date
pip install --upgrade pip

# Check for conflicting requirements
pip check
```

**Node.js: npm install fails**
```bash
# Clear npm cache
npm cache clean --force

# Check Node version
node --version

# Try fresh install
rm -rf node_modules package-lock.json
npm install
```

**Ruby: bundle install fails**
```bash
# Check Ruby/Bundler versions
ruby --version
bundler --version

# Clear bundle cache
bundle clean --force
```

### Application Won't Start

#### Symptom
Build succeeds but application shows as "stopped" or returns 502 errors.

#### Diagnosis
```bash
# Check application state
hop3 app status --app myapp

# Check process logs
hop3 app logs --app myapp --lines 50

# Check uWSGI status
systemctl status uwsgi-hop3
```

#### Common Causes & Solutions

**Missing Procfile:**
```bash
# Verify Procfile exists
cat /home/hop3/apps/myapp/src/Procfile

# Procfile format should be:
# web: gunicorn app:app
```

**Wrong worker command:**
```bash
# Test command manually
cd /home/hop3/apps/myapp/src
source ../venv/bin/activate
<your-command>  # e.g., gunicorn app:app
```

**Port binding issues:**
```bash
# Check if port is in use
ss -tlnp | grep <port>

# Verify PORT environment variable
hop3 env show --app myapp | grep PORT
```

**Missing environment variables:**
```bash
# List all config
hop3 env show --app myapp

# Set missing variables
hop3 env set --app myapp KEY=value
```

### 502 Bad Gateway

#### Symptom
Nginx returns 502 Bad Gateway error.

#### Diagnosis
```bash
# Check Nginx error log
sudo tail -50 /var/log/nginx/error.log

# Check if application socket exists
ls -la /tmp/uwsgi-*.sock

# Check Nginx configuration
sudo nginx -t
```

#### Common Causes & Solutions

**Application not running:**
```bash
# Restart application
hop3 app restart --app myapp

# Check if it started
hop3 app status --app myapp
```

**Socket permission issues:**
```bash
# Check socket permissions
ls -la /tmp/uwsgi-myapp.sock

# Should be owned by hop3:www-data
```

**uWSGI worker crashed:**
```bash
# Check uWSGI logs
sudo journalctl -u uwsgi-hop3 -n 50

# Restart uWSGI
sudo systemctl restart uwsgi-hop3
```

**Nginx config error:**
```bash
# Test configuration
sudo nginx -t

# Reload after fixing
sudo systemctl reload nginx
```

### 404 Not Found

#### Symptom
Application returns 404 for all routes.

#### Diagnosis
```bash
# Check if app has HOST_NAME configured
hop3 env show --app myapp | grep HOST_NAME

# Verify Nginx config exists
ls /home/hop3/nginx/myapp.conf
```

#### Common Causes & Solutions

**Missing HOST_NAME:**
```bash
# Set hostname
hop3 env set --app myapp HOST_NAME=myapp.example.com

# Redeploy
hop3 deploy --app myapp
```

**DNS not configured:**
```bash
# Check DNS resolution
dig myapp.example.com

# Should return your server's IP
```

**Wrong Nginx server_name:**
```bash
# Check Nginx config
grep server_name /home/hop3/nginx/myapp.conf
```

## Database Issues

### Cannot Connect to Database

#### Symptom
Application fails to connect to PostgreSQL or MySQL.

#### Diagnosis
```bash
# Check database addon
hop3 addon list

# Check if DATABASE_URL is set
hop3 env show --app myapp | grep DATABASE

# Test database service
hop3 system status
```

#### Common Causes & Solutions

**Addon not attached:**
```bash
# Attach addon to app
hop3 addon attach mydb --app myapp

# Redeploy to pick up DATABASE_URL
hop3 deploy --app myapp
```

**Database service not running:**
```bash
# PostgreSQL
sudo systemctl status postgresql
sudo systemctl start postgresql

# MySQL
sudo systemctl status mysql
sudo systemctl start mysql
```

**Wrong credentials:**
```bash
# Check addon info
hop3 addon show mydb

# Verify DATABASE_URL format
# postgresql://user:pass@host:port/dbname
```

**PostgreSQL: No pg_hba.conf entry:**
```bash
# Edit pg_hba.conf
sudo nano /etc/postgresql/*/main/pg_hba.conf

# Add lines for Docker networks:
# host all all 172.16.0.0/12 md5
# host all all 192.168.0.0/16 md5

# Reload PostgreSQL
sudo systemctl reload postgresql
```

### Database Connection Timeout

#### Symptom
Application hangs trying to connect to database.

#### Solutions
```bash
# Check if database is listening
ss -tlnp | grep 5432  # PostgreSQL
ss -tlnp | grep 3306  # MySQL

# Check firewall
sudo ufw status

# Verify bind address in config
# PostgreSQL: /etc/postgresql/*/main/postgresql.conf
# listen_addresses = '*'
```

## SSL/TLS Issues

### Certificate Not Provisioned

#### Symptom
Site shows "Not Secure" or SSL certificate errors.

#### Diagnosis
```bash
# Check certificate status
sudo certbot certificates

# Check for errors
sudo journalctl -u certbot -n 50
```

#### Solutions

**DNS not propagated:**
```bash
# Verify DNS
dig myapp.example.com

# Wait for propagation (up to 48 hours)
```

**Port 80 blocked:**
```bash
# Check firewall
sudo ufw status

# Allow HTTP
sudo ufw allow 80/tcp
```

**Rate limited by Let's Encrypt:**
- Wait 1 hour and try again
- Check https://letsencrypt.org/docs/rate-limits/

### Certificate Renewal Failed

#### Solutions
```bash
# Test renewal
sudo certbot renew --dry-run

# Force renewal
sudo certbot renew --force-renewal

# Check timer
systemctl status certbot.timer
```

## Performance Issues

### Application Slow

#### Diagnosis
```bash
# Check resource usage
top
htop

# Check disk I/O
iostat -x 1

# Check application logs for slow queries
hop3 app logs --app myapp | grep -i slow
```

#### Solutions

**Increase workers:**
```bash
hop3 env set --app myapp UWSGI_PROCESSES=4
hop3 app restart --app myapp
```

**Enable caching:**
```bash
# Add Redis
hop3 addon create redis myapp-cache
hop3 addon attach myapp-cache --app myapp
```

**Database optimization:**
```bash
# Check slow queries (PostgreSQL)
sudo -u postgres psql -c "SELECT * FROM pg_stat_statements ORDER BY total_time DESC LIMIT 10;"
```

### Out of Memory

#### Diagnosis
```bash
# Check memory usage
free -h

# Check for OOM killer
dmesg | grep -i oom
```

#### Solutions
```bash
# Add swap space
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile

# Reduce worker memory
hop3 env set --app myapp UWSGI_PROCESSES=2
```

### Disk Full

#### Diagnosis
```bash
# Check disk usage
df -h

# Find large files
du -sh /home/hop3/apps/* | sort -h
du -sh /var/log/* | sort -h
```

#### Solutions
```bash
# Clean old logs
sudo journalctl --vacuum-time=7d

# Clean Docker (if used)
docker system prune -a

# Remove old deployments
# (Be careful - only remove apps you don't need)
```

## Networking Issues

### App Not Accessible Externally

#### Diagnosis
```bash
# Check if app listens on correct interface
ss -tlnp | grep <port>

# Check firewall
sudo ufw status
```

#### Solutions

**Configure a hostname:**
```bash
# Apps bind to 127.0.0.1:$PORT and are reached through the reverse proxy.
# External access comes from setting HOST_NAME and pointing DNS at the server,
# not from exposing the app port directly.
hop3 env set --app myapp HOST_NAME=myapp.example.com
hop3 deploy --app myapp
```

**Open firewall:**
```bash
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
```

### DNS Resolution Issues

#### Diagnosis
```bash
# Check DNS
dig myapp.example.com

# Check /etc/hosts
cat /etc/hosts
```

#### Solutions
```bash
# Verify DNS A record points to server IP
# Check with your DNS provider

# For testing, add to /etc/hosts on client:
# <server-ip> myapp.example.com
```

## Service Issues

### hop3-server Won't Start

#### Diagnosis
```bash
systemctl status hop3-server
journalctl -u hop3-server -n 50
```

#### Solutions

**Configuration error:**
```bash
# Validate config
cat /home/hop3/hop3-server.toml

# Check for syntax errors (TOML format)
```

**Database locked:**
```bash
# Check for stale locks
lsof /home/hop3/hop3.db

# If locked, stop all services and restart
sudo systemctl stop hop3-server uwsgi-hop3
sudo systemctl start hop3-server uwsgi-hop3
```

### Nginx Won't Start

#### Diagnosis
```bash
sudo nginx -t
journalctl -u nginx -n 50
```

#### Solutions

**Configuration syntax error:**
```bash
# Find the error (nginx -t prints the absolute path of the broken file)
sudo nginx -t

# Per-app configs generated by Hop3 live in /home/hop3/nginx/
sudo nano /home/hop3/nginx/<app>.conf
```

**Port already in use:**
```bash
ss -tlnp | grep :80
# Kill the process using the port, or change Nginx port
```

### uWSGI Won't Start

#### Diagnosis
```bash
systemctl status uwsgi-hop3
journalctl -u uwsgi-hop3 -n 50
```

#### Solutions

**Socket directory missing:**
```bash
sudo mkdir -p /run/uwsgi
sudo chown hop3:www-data /run/uwsgi
```

**Configuration error:**
```bash
# Check all app configs (active configs live in uwsgi-enabled)
ls /home/hop3/uwsgi-enabled/
cat /home/hop3/uwsgi-enabled/*.ini
```

## Related Guides

- **[User Guide](user-guide.md)** - Core concepts and daily operations
- **[Administration Guide](administration.md)** - Server configuration and management
- **[Backup and Restore](backup-restore.md)** - Data protection and recovery
- **[CLI Reference](../reference/cli.md)** - Complete command documentation
- **[FAQ](faq.md)** - Quick answers to common questions

## Getting More Help

### Collect Diagnostic Information

```bash
# Full diagnostic dump
hop3 system info >  diagnostic.txt
hop3 system status >> diagnostic.txt
hop3 app list >> diagnostic.txt

# Include logs for specific app
hop3 app logs --app myapp --lines 200 >> diagnostic.txt
```

### Where to Get Help

1. **Documentation**: https://hop3.cloud/
2. **GitHub Issues**: https://github.com/hop3-project/hop3/issues
3. **Community Chat**: (link to Discord/Matrix if available)

When reporting issues, please include:
- Hop3 version: `hop3 --version`
- Operating system: `cat /etc/os-release`
- Error messages and logs
- Steps to reproduce
