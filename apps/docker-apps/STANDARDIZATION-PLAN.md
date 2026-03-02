# Dockerfile Standardization Plan

## Overview

This document outlines the plan to standardize all 31 Docker-based application Dockerfiles in the hop3 NGI apps collection.

## Current State Analysis

### Language Distribution
| Category | Count | Apps |
|----------|-------|------|
| PHP (Apache) | 10 | bookstack, wordpress, easy-appointments, kanboard, matomo, invoice-ninja, monica, dolibarr, limesurvey, nextcloud |
| Node.js | 7 | etherpad, cryptpad, formbricks, hedgedoc, wiki-js, umami, ghost |
| Go | 5 | grafana, focalboard, mattermost, gitea, vikunja |
| Python | 4 | searxng, matrix-synapse, radicale, isso |
| Java | 3 | sonarqube, jenkins, xwiki |
| Ruby | 1 | mastodon |

### Web Server Distribution
| Type | Count | Apps |
|------|-------|------|
| Apache + mod_php | 10 | All PHP apps |
| Built-in server | 21 | All others |

---

## Key Issues to Address

### Issue 1: Apache Port Configuration

**Current State:** Apache apps hardcode `Listen 8080` in the Apache config at build time.

**Why It Works:** Docker handles port mapping externally. The container always listens on 8080 internally, and `docker run -p HOST_PORT:8080` maps the external port. Hop3's docker-compose generation does:
```yaml
ports:
  - "127.0.0.1:${PORT:-8080}:8080"
```

So the HOST_PORT is dynamic, but the container port is always 8080.

**Is This Actually a Problem?**
- **For Hop3:** No - Docker handles the mapping, the internal port doesn't matter
- **For Consistency:** Minor - built-in server apps use `PORT` env var, Apache apps don't
- **For Flexibility:** Minimal impact - there's rarely a need to change internal container port

**Decision:** LOW PRIORITY. Keep hardcoded 8080 for Apache apps. The docker-compose port mapping handles everything. Document this as intentional: Apache apps use fixed internal port 8080, mapped externally by Docker.

**Action:** Add comment to Apache Dockerfiles explaining this is intentional.

### Issue 2: Environment Variable Defaults

**Problem:** Some Dockerfiles provide default values for environment variables that MUST be supplied by Hop3. This is dangerous because:
- Redundant at best
- Masks configuration errors at worst
- Can cause subtle bugs (e.g., app starts with wrong database)

**Current Anti-Pattern:**
```bash
export DATABASE_URL="${DATABASE_URL:-postgresql://localhost/app}"
```

If Hop3 fails to inject DATABASE_URL, the app silently uses localhost and fails mysteriously later.

**Correct Pattern:**
```bash
# Required - fail immediately if not set
: "${DATABASE_URL:?ERROR: DATABASE_URL is required}"

# Optional - default is fine
export LOG_LEVEL="${LOG_LEVEL:-info}"
```

**Categories of Environment Variables:**

| Category | Default? | Example |
|----------|----------|---------|
| Database connection (from addon) | NO | DATABASE_URL, PGHOST, MYSQL_HOST |
| App secrets (from Hop3) | NO | SECRET_KEY, JWT_SECRET |
| Runtime port | NO | PORT (always injected by Hop3) |
| App behavior (optional) | YES | LOG_LEVEL, DEBUG, WORKERS |
| Build-time only | YES | VERSION numbers for downloads |

### Issue 3: Smoke Test Compatibility

**Requirement:** `docker build .` must succeed without any environment variables.

**Requirement:** `docker run <image>` without required env vars must FAIL FAST with clear error.

**Solution:**
- Build-time: Use ARG with defaults for version numbers, download URLs
- Run-time: Startup script validates required env vars before starting app

**Build-Time (OK to have defaults):**
```dockerfile
ARG APP_VERSION=1.2.3
RUN curl -L "https://example.com/app-${APP_VERSION}.tar.gz" | tar xz
```

**Run-Time (NO defaults for required vars):**
```bash
#!/bin/bash
set -e

# Validate required environment variables
: "${PORT:?ERROR: PORT is required}"
: "${DATABASE_URL:?ERROR: DATABASE_URL is required}"
: "${SECRET_KEY:?ERROR: SECRET_KEY is required}"

# Optional with defaults
export LOG_LEVEL="${LOG_LEVEL:-info}"
export WORKERS="${WORKERS:-4}"

# Start application
exec ...
```

---

## Standardization Specifications

### 1. Base Image (Already Consistent)
```dockerfile
FROM debian:trixie-slim
ENV DEBIAN_FRONTEND=noninteractive
```

### 2. Apt Installation Pattern (Already Consistent)
```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends \
    package1 \
    package2 \
    && rm -rf /var/lib/apt/lists/*
```

### 3. User Creation Pattern

**Standard Pattern:**
```dockerfile
RUN useradd -m -d /home/<appname> -s /bin/bash <appname>
```

**For PHP/Apache apps:**
```dockerfile
# Use existing www-data user, no creation needed
```

### 4. Startup Script Pattern

**Preferred Method:** COPY from template file (for complex scripts)
```dockerfile
COPY start.sh /usr/local/bin/start-<appname>.sh
RUN chmod +x /usr/local/bin/start-<appname>.sh
CMD ["/usr/local/bin/start-<appname>.sh"]
```

**Alternative Method:** Inline printf (for simple scripts)
```dockerfile
RUN printf '%s\n' \
    '#!/bin/bash' \
    'set -e' \
    '' \
    '# Validate required vars' \
    ': "${PORT:?ERROR: PORT is required}"' \
    '' \
    '# Start app' \
    'exec su appuser -c "app-command"' \
    > /usr/local/bin/start-appname.sh \
    && chmod +x /usr/local/bin/start-appname.sh
```

**NOT Recommended:** echo with backslash escapes (error-prone)
```dockerfile
# AVOID THIS - hard to read and maintain
RUN echo '#!/bin/bash\n\
set -e\n\
...' > /script.sh
```

### 5. Startup Script Template

```bash
#!/bin/bash
set -e

# ==============================================================================
# Required Environment Variables (injected by Hop3)
# ==============================================================================
: "${PORT:?ERROR: PORT is required}"
# Add other required vars based on app needs:
# : "${DATABASE_URL:?ERROR: DATABASE_URL is required}"
# : "${SECRET_KEY:?ERROR: SECRET_KEY is required}"

# ==============================================================================
# Optional Environment Variables (with sensible defaults)
# ==============================================================================
export LOG_LEVEL="${LOG_LEVEL:-info}"
# Add other optional vars

# ==============================================================================
# Configuration
# ==============================================================================
# Generate config files from templates if needed
# envsubst < /path/to/config.template > /path/to/config

# ==============================================================================
# Permissions
# ==============================================================================
chown -R <appuser>:<appuser> /path/to/data

# ==============================================================================
# Start Application
# ==============================================================================
exec su <appuser> -c "<start-command>"
```

### 6. Configuration File Management

**Pattern A: Runtime envsubst (Preferred for complex configs)**
```dockerfile
COPY config.template /etc/app/config.template
# In startup script:
# envsubst < /etc/app/config.template > /etc/app/config
```

**Pattern B: Environment-aware app (No config file needed)**
```dockerfile
# App reads from environment directly
# Just set env vars in docker-compose
```

**Pattern C: Inline creation (Only for very simple configs)**
```bash
# In startup script:
cat > /etc/app/config <<EOF
setting1 = ${VAR1}
setting2 = ${VAR2}
EOF
```

### 7. Port Configuration

**For Built-in Server Apps:**
```dockerfile
# Build-time: document the default but don't set it
# (PORT is always provided by Hop3 at runtime)
EXPOSE 8080
```

```bash
# Runtime: require PORT
: "${PORT:?ERROR: PORT is required}"
exec app --port="${PORT}"
```

**For Apache Apps:**
```dockerfile
# Fixed internal port - Docker handles external mapping
RUN echo 'Listen 8080' > /etc/apache2/ports.conf
EXPOSE 8080
CMD ["apache2ctl", "-D", "FOREGROUND"]
```

### 8. Database Configuration

**Required Variables (NO defaults):**
```bash
# PostgreSQL addon
: "${PGHOST:?ERROR: PGHOST is required}"
: "${PGPORT:?ERROR: PGPORT is required}"
: "${PGDATABASE:?ERROR: PGDATABASE is required}"
: "${PGUSER:?ERROR: PGUSER is required}"
: "${PGPASSWORD:?ERROR: PGPASSWORD is required}"

# MySQL addon
: "${MYSQL_HOST:?ERROR: MYSQL_HOST is required}"
: "${MYSQL_PORT:?ERROR: MYSQL_PORT is required}"
: "${MYSQL_DATABASE:?ERROR: MYSQL_DATABASE is required}"
: "${MYSQL_USER:?ERROR: MYSQL_USER is required}"
: "${MYSQL_PASSWORD:?ERROR: MYSQL_PASSWORD is required}"
```

**Building DATABASE_URL from components (if app needs it):**
```bash
export DATABASE_URL="postgresql://${PGUSER}:${PGPASSWORD}@${PGHOST}:${PGPORT}/${PGDATABASE}"
```

---

## Implementation Plan

### Phase 1: Documentation & Templates
- [ ] Create standard startup script templates for each language category
- [ ] Document required vs optional env vars for each app
- [ ] Add standardization comments to existing Dockerfiles

### Phase 2: Fix Critical Issues
- [ ] Remove dangerous default values for required env vars
- [ ] Add proper validation (`: "${VAR:?ERROR}"`) to all startup scripts
- [ ] Ensure all apps fail fast with clear errors when misconfigured

### Phase 3: Consistency Improvements
- [ ] Convert echo-based scripts to printf or COPY pattern
- [ ] Standardize user creation across all apps
- [ ] Add config templates where missing

### Phase 4: Testing
- [ ] Verify `docker build .` succeeds for all 31 apps
- [ ] Verify `docker run` without env vars fails with clear error
- [ ] Verify full deployment through Hop3 works

---

## App-Specific Notes

### PHP/Apache Apps (10)
- Use www-data user (no creation needed)
- Fixed port 8080 (Docker handles mapping)
- Most need startup scripts for database config

**Missing startup scripts (need to add):**
- wordpress
- kanboard
- nextcloud

### Node.js Apps (7)
- Use dedicated app user
- Read PORT from environment
- Most need DATABASE_URL or PG* vars

### Go Apps (5)
- Use dedicated app user
- Single binary, simple startup
- Most read DATABASE_URL directly

### Python Apps (4)
- Use venv with --system-site-packages (for pkg_resources compatibility)
- Use dedicated app user
- Config file based

### Java Apps (3)
- Use dedicated app user
- Need JAVA_OPTS for memory configuration
- Config templates with envsubst

### Ruby Apps (1 - Mastodon)
- Complex setup with assets
- Multiple required env vars
- Already has good validation

---

## Validation Checklist (per app)

- [ ] Base image: `debian:trixie-slim`
- [ ] DEBIAN_FRONTEND=noninteractive
- [ ] Apt cleanup: `rm -rf /var/lib/apt/lists/*`
- [ ] User creation: standard pattern or www-data
- [ ] Startup script: exists and uses standard template
- [ ] Required env vars: validated with `: "${VAR:?ERROR}"`
- [ ] No dangerous defaults for required vars
- [ ] EXPOSE 8080
- [ ] CMD uses startup script or direct command
- [ ] `docker build .` succeeds
- [ ] `docker run` without env vars fails with clear error
