# Hop3 Deployment Testing Scripts

This directory contains scripts for testing Hop3 deployments on a dockerized test server.

## Prerequisites

- Docker installed and running
- `uv` package manager installed
- Project built with `make build`

## Available Scripts

### 1. Single App Deployment Test (`test-deployment-manual.sh`)

Tests deploying a single Flask application with full HTTP access verification.

**Usage:**
```bash
./scripts/test-deployment-manual.sh
```

**Features:**
- Creates a test Flask application with:
  - Home page at `/`
  - Health check at `/health`
  - API endpoint at `/api/info`
- Deploys via hop3 CLI
- Verifies deployment status
- Tests HTTP access via nginx virtual host
- Provides debugging information

**Output:**
- Application deployed and accessible at `http://localhost:8080/` (with `Host: testapp.local` header)
- Full nginx and uwsgi configuration details
- Interactive instructions for further testing

**Cleanup:**
```bash
docker stop hop3-manual-test && docker rm hop3-manual-test
```

### 2. Multi-App Deployment Test (`test-deployment-multi-app.sh`)

Tests deploying two applications simultaneously to verify multi-tenancy.

**Usage:**
```bash
./scripts/test-deployment-multi-app.sh
```

**Features:**
- Deploys two Flask applications:
  - **blueapp**: Blue-themed application
  - **greenapp**: Green-themed application
- Each app has unique:
  - Name and theme color
  - API endpoints returning app-specific data
  - Health check endpoints
- Tests simultaneous operation
- Verifies both apps are accessible

**Output:**
- Both applications deployed and running
- Status for each application
- HTTP access tests for both apps
- Nginx configuration for both apps

**Known Limitations:**
- Virtual host routing: Both apps currently use default `server_name _` (catch-all), so nginx routes all requests to the first app encountered. To properly test virtual host isolation, apps need unique `NGINX_SERVER_NAME` values.

**Cleanup:**
```bash
docker stop hop3-multi-test && docker rm hop3-multi-test
```

## Test Architecture

Both scripts use the same Docker-based test infrastructure:

- **Base Image**: Ubuntu 22.04
- **Services** (managed by supervisord):
  - SSH server (for hop3 CLI access)
  - Nginx (for HTTP reverse proxy)
  - uWSGI Emperor (for app process management)
  - Hop3 Server (for deployment management)

### Port Mapping

Default ports (with automatic fallback to random ports if occupied):
- **22 → 2222**: SSH access for hop3 CLI
- **80 → 8080**: HTTP access via nginx
- **8000 → 8000**: Hop3 API server

## Deployment Flow

1. **Setup Phase**:
   - Build Docker image with hop3-server
   - Start container with supervisord managing all services
   - Wait for services to initialize

2. **App Creation Phase**:
   - Create Flask application with test code
   - Initialize git repository
   - Configure virtual host via `env` file

3. **Deployment Phase**:
   - Deploy via `hop3 deploy` CLI command (RPC over SSH)
   - Wait for app to start (uwsgi vassal spawning)
   - Verify deployment status

4. **Testing Phase**:
   - Check app status via hop3 CLI
   - Test HTTP access via nginx
   - Verify health endpoints
   - Check nginx and uwsgi configuration

## Common Issues

### Port Conflicts

If you see port allocation errors, the scripts automatically detect conflicts and use random ports. Check the output for actual ports used.

### HTTP 502 Bad Gateway

This typically means:
1. uWSGI vassal hasn't started yet (wait 10-30 seconds)
2. uWSGI emperor failed to spawn the vassal (check logs)

**Debug commands:**
```bash
# Check uwsgi emperor status
docker exec <container> supervisorctl status uwsgi

# Check uwsgi logs
docker exec <container> cat /var/log/supervisor/uwsgi_err.log

# Check app-specific logs
docker exec <container> cat /home/hop3/apps/<appname>/log/web.1.log
```

### Virtual Host Routing

To properly test virtual host routing with multiple apps:

1. Each app needs a unique `NGINX_SERVER_NAME` in its `env` file
2. Add entries to `/etc/hosts`:
   ```bash
   echo '127.0.0.1 app1.local app2.local' | sudo tee -a /etc/hosts
   ```
3. Access via hostname:
   ```bash
   curl http://app1.local:8080/
   curl http://app2.local:8080/
   ```

## Development Workflow

1. **Make changes** to hop3-server code
2. **Rebuild** the distribution:
   ```bash
   make build
   ```
3. **Remove old Docker image** to force rebuild:
   ```bash
   docker rmi hop3-e2e:test
   ```
4. **Run test script** to verify changes:
   ```bash
   ./scripts/test-deployment-manual.sh
   ```

## Automated E2E Tests

For automated testing, use pytest:

```bash
# Run single deployment test
uv run pytest packages/hop3-server/tests/d_e2e/test_python_deployment.py -v

# Run with verbose output
uv run pytest packages/hop3-server/tests/d_e2e/test_python_deployment.py -v -s
```

The automated tests use the same Docker infrastructure but with pytest fixtures for setup/teardown.

## Next Steps

- Add more test scripts for different app types (Ruby, Node.js, etc.)
- Implement proper virtual host routing tests
- Add load testing scenarios
- Test database connectivity (PostgreSQL)
- Test SSL/TLS certificate generation
- Test app updates and rollbacks
