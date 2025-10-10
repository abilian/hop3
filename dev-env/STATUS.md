# Hop3 Development Environment - Status

**Last Updated**: 2025-10-10

## Current Status

The development environment allows complete end-to-end deployment working!

### What's Working

**1. All Core Services**
- **hop3-server** (port 8000) - JSON-RPC API accessible from host
- **nginx** (ports 8080/8443) - HTTP/HTTPS working, automatic reload
- **uwsgi-emperor** - App workers start correctly
- **PostgreSQL** (port 5432) - Database accessible
- **SSH** (port 2222) - Remote access working

**2. Complete Deployment Workflow**
- Deploy from host machine via `hop deploy`
- Files upload correctly
- Virtual environment creation works
- Dependencies install correctly
- uWSGI configs generated in `uwsgi-available/`
- Nginx configs generated in `nginx/`
- **Nginx automatically reloads** after config changes
- Apps start with workers
- **Apps accessible via HTTP** at localhost:8080

**3. All Management Scripts**
- `setup.sh` - Builds Docker image
- `start.sh` - Starts container with health checks
- `stop.sh` - Stops container gracefully
- `rebuild.sh` - Rebuilds after code changes
- `status.sh` - Shows service status
- `shell.sh` - Opens shell in container
- `logs.sh` - Views service logs
- `test.sh` - Tests service accessibility
- `run.sh` - Runs arbitrary commands
- `setup-cli.sh` - Configures hop CLI on host

**4. hop CLI Integration**
- CLI connects to containerized server
- Authentication disabled for dev (HOP3_ENABLE_AUTH=false)
- All commands work: deploy, apps, app:status, app:logs, etc.
- Config file: `~/Library/Application Support/hop3-cli/config.toml`


## Testing the Environment

### Quick Test

```bash
cd dev-env
./start.sh

# Deploy test app
hop deploy testapp apps/flask-gunicorn-pip-no-config

# Access immediately
curl http://localhost:8080/
# Returns: Hello World!

# Check status
hop apps
# Shows: testapp (RUNNING, 1 worker)
```

### Verification Commands

```bash
# Check all services are running
./status.sh

# Check nginx config was created
docker exec hop3-dev ls -la /home/hop3/.hop3/nginx/
# Shows: testapp.conf, testapp.crt, testapp.key

# Check nginx reloaded automatically
./logs.sh hop3-server | grep nginx
# Shows: "nginx reloaded via supervisorctl"

# Test HTTP access
curl http://localhost:8080/
# Returns app response
```

## Known Limitations

### 1. Multi-App Hostnames

**Issue**: All apps default to `server_name _;` (catch-all), so only one responds.

**Workaround**: Configure unique hostnames in `/etc/hosts`:

```bash
# Add to /etc/hosts
127.0.0.1 app1.local app2.local

# Access specific apps
curl -H "Host: app1.local" http://localhost:8080/
curl -H "Host: app2.local" http://localhost:8080/
```

**Proper Fix**: Implement `hop config:set` command to set `NGINX_SERVER_NAME` per-app.

### 2. Port/Hostname Display

**Issue**: `hop app:status` shows "Port: not assigned" even though port is assigned.

**Impact**: Cosmetic only - apps work fine.

**Root Cause**: Port is assigned in environment but not saved to database.

## Architecture

### Port Mapping

```
Host              Container
---------------------------------
localhost:8000 -> 8000 (hop3-server JSON-RPC API)
localhost:8080 -> 80   (nginx HTTP)
localhost:8443 -> 443  (nginx HTTPS, self-signed)
localhost:2222 -> 22   (SSH)
localhost:5432 -> 5432 (PostgreSQL)
```

### File Locations (inside container)

```
/home/hop3/.hop3/
├── apps/             # Deployed applications
│   └── myapp/
│       ├── src/      # Source code
│       ├── venv/     # Python virtualenv
│       ├── log/      # uWSGI logs
│       └── data/     # Persistent data
├── cache/            # Build cache
├── certificates/     # Self-signed SSL certs
├── nginx/            # Nginx configs (*.conf, *.crt, *.key)
├── uwsgi/            # uWSGI emperor config
├── uwsgi-available/  # Available app configs
└── uwsgi-enabled/    # Enabled app configs (symlinks)
```

### Deployment Flow

1. **Host**: Run `hop deploy myapp /path/to/app`
2. **hop CLI**: Creates tar.gz, sends to http://localhost:8000/rpc
3. **hop3-server**: Receives files via JSON-RPC
4. **Extraction**: Files extracted to `/home/hop3/.hop3/apps/myapp/src/`
5. **Build**: Creates virtualenv, installs dependencies
6. **uWSGI Config**: Writes `uwsgi-available/myapp_web.1.ini`
7. **Symlink**: Creates `uwsgi-enabled/myapp_web.1.ini` → `../uwsgi-available/...`
8. **Nginx Config**: Writes `nginx/myapp.conf` with proxy settings
9. **SSL Certs**: Generates self-signed `myapp.crt` and `myapp.key`
10. **Reload Nginx**: Runs `sudo supervisorctl restart nginx`
11. **uWSGI Start**: Emperor detects new config, starts workers
12. **Ready**: App accessible at http://localhost:8080/

## Next Steps

1. **High Priority**: Change NGINX_SERVER_NAME default from `_` to `{appname}.hop3`
2. **High Priority**: Save port/hostname to database for status display
3. **High Priority**: Implement `hop config:set` command
4. **Medium**: HTTPS testing, documentation updates

## Testing Notes

- All nginx unit tests pass (5 tests in 0.20s)
- Tests skip nginx reload (detect PYTEST_CURRENT_TEST env var)
- No password prompts during testing (sudo -n flag)
- Automatic nginx reload works in container (supervisorctl with sudo)
- Graceful fallback if nginx reload fails

## Success Metrics

At this point, we can successfully:

1. **Deploy applications** using `hop deploy` from host machine
2. **Access apps via HTTP** at localhost:8080
3. **View application status** with accurate worker counts
4. **View application logs**
5. **Redeploy applications** with automatic restart
6. **Test full production-like workflow** without root on host
