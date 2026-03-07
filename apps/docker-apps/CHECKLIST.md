# Docker App Checklist

Quick reference for creating or reviewing Docker-based apps for Hop3:

- [ ] Base image is `debian:trixie-slim`
- [ ] `DEBIAN_FRONTEND=noninteractive` is set
- [ ] Apt lists cleaned: `rm -rf /var/lib/apt/lists/*`
- [ ] User created with standard pattern (or uses www-data)
- [ ] `EXPOSE 8080` present
- [ ] Startup script exists and is executable
- [ ] `CMD` runs the startup script
- [ ] Required env vars validated with `: "${VAR:?ERROR}"`
- [ ] No dangerous defaults for DATABASE_URL, SECRET_KEY, etc.
- [ ] `docker build .` succeeds without env vars
- [ ] `docker run <image>` fails fast with clear error when env vars missing
- [ ] Full deployment through Hop3 works

Rationale below.

---

## Dockerfile Requirements

### Base Image
```dockerfile
FROM debian:trixie-slim
ENV DEBIAN_FRONTEND=noninteractive
```

### Apt Installation
```dockerfile
RUN apt-get update -q && apt-get install -q -y --no-install-recommends \
    package1 \
    package2 \
    && rm -rf /var/lib/apt/lists/*
```
- Use `-q` (quiet) flag to reduce build log noise
- Always clean up apt lists to minimize image size

### User Creation

**For PHP/Apache apps:** Use existing `www-data` user (no creation needed)

**For all other apps:**
```dockerfile
RUN useradd -m -d /home/appname -s /bin/bash appname
```

### Port Configuration
```dockerfile
EXPOSE 8080
```
All apps use port 8080 internally. Docker/Hop3 handles external port mapping.

### Startup Script
```dockerfile
COPY start.sh /usr/local/bin/start-appname.sh
RUN chmod +x /usr/local/bin/start-appname.sh
CMD ["/usr/local/bin/start-appname.sh"]
```

---

## Startup Script Requirements (`start.sh`)

### Template
```bash
#!/bin/bash
set -e

# ==============================================================================
# Required Environment Variables (fail fast if missing)
# ==============================================================================
: "${PORT:?ERROR: PORT is required}"
# Add database vars based on addon type - see below

# ==============================================================================
# Optional Environment Variables (sensible defaults OK)
# ==============================================================================
export LOG_LEVEL="${LOG_LEVEL:-info}"
export WORKERS="${WORKERS:-4}"

# ==============================================================================
# Configuration (generate config files if needed)
# ==============================================================================
# envsubst < /path/to/config.template > /path/to/config

# ==============================================================================
# Permissions
# ==============================================================================
chown -R appname:appname /path/to/data

# ==============================================================================
# Start Application
# ==============================================================================
exec su appname -c "app-command --port=${PORT}"
```

### Environment Variable Rules

| Category | Default OK? | Example |
|----------|-------------|---------|
| Database connection | **NO** | DATABASE_URL, PGHOST, MYSQL_HOST |
| App secrets | **NO** | SECRET_KEY, JWT_SECRET |
| Runtime port | **NO** | PORT |
| App behavior | YES | LOG_LEVEL, DEBUG, WORKERS |
| Build-time versions | YES | APP_VERSION (use ARG) |

**Required vars must fail immediately:**
```bash
: "${DATABASE_URL:?ERROR: DATABASE_URL is required}"
```

**Never set dangerous defaults:**
```bash
# WRONG - masks configuration errors
export DATABASE_URL="${DATABASE_URL:-postgresql://localhost/app}"

# CORRECT - fails fast with clear error
: "${DATABASE_URL:?ERROR: DATABASE_URL is required}"
```

---

## Database Configuration

### PostgreSQL Addon
```bash
: "${PGHOST:?ERROR: PGHOST is required}"
: "${PGPORT:?ERROR: PGPORT is required}"
: "${PGDATABASE:?ERROR: PGDATABASE is required}"
: "${PGUSER:?ERROR: PGUSER is required}"
: "${PGPASSWORD:?ERROR: PGPASSWORD is required}"

# Build DATABASE_URL if app needs it
export DATABASE_URL="postgresql://${PGUSER}:${PGPASSWORD}@${PGHOST}:${PGPORT}/${PGDATABASE}"
```

### MySQL Addon
```bash
: "${MYSQL_HOST:?ERROR: MYSQL_HOST is required}"
: "${MYSQL_PORT:?ERROR: MYSQL_PORT is required}"
: "${MYSQL_DATABASE:?ERROR: MYSQL_DATABASE is required}"
: "${MYSQL_USER:?ERROR: MYSQL_USER is required}"
: "${MYSQL_PASSWORD:?ERROR: MYSQL_PASSWORD is required}"
```

---

## Config File Management

**Option A: Runtime envsubst (preferred for complex configs)**
```dockerfile
COPY config.template /etc/app/config.template
```
```bash
# In start.sh
envsubst < /etc/app/config.template > /etc/app/config
```

**Option B: Environment-aware app (no config file)**
```bash
# App reads from environment directly - just validate vars
```

**Option C: Inline creation (simple configs only)**
```bash
cat > /etc/app/config <<EOF
setting1 = ${VAR1}
setting2 = ${VAR2}
EOF
```

---

## Apache/PHP Apps

PHP apps use Apache with fixed internal port 8080:

```dockerfile
# Configure Apache for port 8080
RUN echo 'Listen 8080' > /etc/apache2/ports.conf
RUN sed -i 's/80/8080/g' /etc/apache2/sites-available/000-default.conf

EXPOSE 8080
CMD ["apache2ctl", "-D", "FOREGROUND"]
```

Startup script still needed for:
- Database configuration (wp-config.php, etc.)
- First-run setup
- Permission fixes

---

## Directory Structure

```
apps/docker-apps/myapp/
├── Dockerfile          # Build instructions
├── hop3.toml           # Hop3 configuration
├── start.sh            # Startup script (copied into image)
└── config.template     # Optional: config template for envsubst
```

### Typical `hop3.toml`
```toml
# Hop3 Configuration for MyApp (Docker-based)
# Dockerfile handles build and runtime; hop3.toml defines metadata and dependencies

[metadata]
id = "myapp"
version = "1.0"
title = "My Application"
description = "Brief description of what the app does"
homepage = "https://example.com/"
license = "MIT"
categories = ["category1", "category2"]

# Database addon - automatically provisioned by hop3 deploy
# Use "postgres" or "mysql" depending on app requirements
[[addons]]
type = "postgres"

# Environment variables injected at deploy time
# (database connection vars are injected automatically by the addon)
[env]
LOG_LEVEL = "info"
SOME_FEATURE = "true"

[healthcheck]
path = "/health"
```
