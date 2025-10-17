# System Integration Tests

This directory contains system integration tests that verify hop3-cli and hop3-server work together correctly, including authentication, RPC communication, and basic command execution.

**Important**: These are **not** full end-to-end tests with actual application deployments. For full E2E tests, see `tests/d_e2e/`.

## Test Scope

System integration tests verify:
- ✅ CLI ↔ Server RPC communication
- ✅ Authentication flow (register, login, token validation)
- ✅ Basic CLI commands execute successfully
- ✅ Basic deployment via tarball (deploy command)
- ✅ Git archive extraction and security
- ❌ No full application lifecycle (start/stop/restart)
- ❌ No nginx/uwsgi configuration tests
- ❌ No systemd service tests

**Note**: Tests requiring full deployment infrastructure (uwsgi, nginx, systemd) have been moved to `tests/d_e2e/test_full_deployment.py`.

## Requirements

1. **Docker** - Required for running tests
   ```bash
   # Verify Docker is installed and running
   docker ps
   ```

2. **hop3-cli binary** - Must be installed and available in PATH:
   ```bash
   pip install -e packages/hop3-cli
   ```

## Running System Integration Tests

### Default: Docker-based testing (Recommended)

```bash
# IMPORTANT: Ensure HOP3_DEV_HOST is NOT set
unset HOP3_DEV_HOST

# Run all system tests
pytest packages/hop3-server/tests/c_system/ -v

# Run specific test
pytest packages/hop3-server/tests/c_system/test_connection.py -v
```

**What happens automatically**:
1. Tests build or reuse `hop3-e2e:test` Docker image
2. Fresh Docker container starts with hop3-server
3. Container is isolated and reproducible
4. Authentication configured automatically
5. All tests run against container
6. Container is cleaned up after tests

**Benefits of Docker-based testing**:
- ✅ No manual server setup required
- ✅ Isolated environment (no conflicts)
- ✅ Reproducible across machines
- ✅ Same infrastructure as d_e2e tests
- ✅ Automatic cleanup

### Optional: Remote Server Diagnostics

Some tests in `test_connection.py` can optionally run against a remote server for diagnostics:

```bash
# Only for remote server diagnostics (not regular testing)
export HOP3_DEV_HOST=hop3@test-server.example.com
pytest packages/hop3-server/tests/c_system/test_connection.py -v
```

⚠️ **WARNING**: Setting `HOP3_DEV_HOST` will cause tests to connect to that remote server instead of using Docker. This is **only** for diagnosing remote server issues, not for regular development or CI/CD.

For CI/CD, **always ensure `HOP3_DEV_HOST` is not set**.

### Skip system tests (run only unit and integration):
```bash
pytest packages/hop3-server/tests/a_unit packages/hop3-server/tests/b_integration
```

## Test Structure

### `conftest.py`
Provides pytest fixtures for Docker-based system integration testing:
- `docker_client()`: Provides Docker client connection
- `hop3_image()`: Builds or reuses `hop3-e2e:test` Docker image (session scope)
- `local_server()`: Starts Docker container with hop3-server (session scope)
- `hop3_config_dir()`: Creates temporary config directory and sets environment variables
- `system_auth_token()`: Registers test user and gets authentication token
- `test_app_dir()`: Creates temporary directory for test data
- `deployed_app()`: Manages app deployment lifecycle and cleanup
- `hop3()`: Helper function to run hop3-cli commands
- `requires_full_infrastructure`: Skip marker for tests requiring uwsgi/nginx/systemd

### `test_connection.py`
Diagnostic tests to verify system setup:
- SSH connectivity (remote servers only)
- CLI availability
- CLI connection to server
- Authentication commands available
- Authentication registration and login

### `test_e2e_deployment.py`
Basic deployment tests (no full infrastructure needed):
- Tarball deployment via `hop3 deploy`
- Application listing via `hop3 apps`
- Authentication requirements

### `test_e2e_git_hook.py`
Git-hook deployment tests (no full infrastructure needed):
- Invalid commit reference handling
- Git archive extraction
- Path traversal prevention
- Authentication requirements

### Tests Moved to `tests/d_e2e/`
The following test categories require full infrastructure and are in `test_full_deployment.py`:
- Application lifecycle (start, stop, restart, status)
- Environment variable management (config:set, config:get, config:unset)
- Application destruction (destroy)
- Web endpoint accessibility
- Full git-hook deployment workflow

## Key Differences: System vs E2E vs Integration

| Aspect | Integration Tests | System Tests | E2E Tests |
|--------|------------------|--------------|-----------|
| **Location** | `tests/b_integration/` | `tests/c_system/` | `tests/d_e2e/` |
| **Server** | TestClient (no process) | Docker container | Docker container |
| **CLI** | Direct function calls | Real hop3-cli binary | Real hop3-cli binary |
| **Network** | In-memory | Real HTTP | Real HTTP/SSH |
| **Deployments** | Mocked | No deployments | Real deployments |
| **Speed** | Very fast (<1s) | Fast (20s + build) | Slow (30-60s) |
| **Isolation** | Complete | Complete (container) | Complete (container) |

## Authentication Flow

1. **Session setup**: Test user is registered via `hop3 auth:register`
2. **Login**: Token obtained via `hop3 auth:login`
3. **Config**: Token set via `HOP3_API_TOKEN` environment variable
4. **All commands**: Use Bearer token authentication automatically
5. **Cleanup**: Test user deleted at end of session

Tests use environment variables (`HOP3_API_URL` and `HOP3_API_TOKEN`) instead of config files for reliability.

## Debugging

### Tests hanging or timing out?

If tests hang for more than 30 seconds:

1. **Check if Docker is running**:
   ```bash
   # Verify Docker daemon is running
   docker ps

   # Check if hop3 container is running
   docker ps | grep hop3-e2e
   ```

2. **Check environment variables**:
   ```bash
   echo $HOP3_API_URL
   echo $HOP3_DEV_HOST  # Should be empty for normal testing!
   ```

3. **Check Docker container logs**:
   ```bash
   # Find the container ID
   docker ps | grep hop3-e2e

   # View container logs
   docker logs <container-id>
   ```

### Verbose test output

Always run with `-s` flag to see progress:
```bash
pytest packages/hop3-server/tests/c_system/ -v -s --tb=short -x
```

Flags explained:
- `-v`: Verbose test names
- `-s`: Show print statements (progress indicators)
- `--tb=short`: Short tracebacks
- `-x`: Stop on first failure

### Test authentication manually:
```bash
# Get the API URL from running test container
docker ps | grep hop3-e2e  # Find the port mapping

# Example: If port 8000 is mapped to 32768
export HOP3_API_URL="http://localhost:32768"
hop3 auth:register testuser test@example.com testpassword
hop3 auth:login testuser testpassword
hop3 apps
```

### Check server logs:
```bash
# Docker container logs
docker logs <container-id>

# Follow logs in real-time
docker logs -f <container-id>

# Check supervisor logs inside container
docker exec <container-id> cat /var/log/supervisor/hop3-server.log
```

### Common timeout causes:

- **"Registering test user" timeout**: Server not responding or auth disabled
- **"Logging in" timeout**: Server not responding, wrong credentials, or missing HOP3_SECRET_KEY
- **"Running: hop3 apps" timeout**: Token not set or invalid

## CI Integration

System integration tests are designed for CI and require **no manual server setup**!

They automatically use Docker to create isolated test environments.

Example GitHub Actions workflow:
```yaml
- name: Run system integration tests
  run: |
    # IMPORTANT: Ensure HOP3_DEV_HOST is not set
    unset HOP3_DEV_HOST
    # Tests automatically build Docker image and start container
    pytest packages/hop3-server/tests/c_system/ -v
```

⚠️ **CI/CD Best Practice**: Always ensure `HOP3_DEV_HOST` environment variable is **not set** when running c_system tests in CI/CD pipelines. This ensures tests use the isolated Docker environment instead of attempting to connect to external servers.

## Server Setup Requirements

### Docker-based Testing (Default & Recommended)

**No setup required!** Tests automatically use Docker for complete isolation:

**What happens automatically**:
1. **Docker Image**: Tests build or reuse `hop3-e2e:test` image (session scope)
2. **Fresh Container**: New container started for each test session
3. **Environment Setup**:
   - Authentication enabled with test secret key
   - Database initialized automatically
   - hop3-server started via supervisor
4. **Environment Variables**: `HOP3_API_URL` and `HOP3_SECRET_KEY` set automatically
5. **Network Isolation**: Tests communicate via HTTP to random host ports
6. **Automatic Cleanup**: Container stopped and removed after tests

**Requirements**:
- Docker daemon running
- `hop3-cli` binary installed (`pip install -e packages/hop3-cli`)

### Remote Server Diagnostics (Optional, Not Recommended)

Some tests in `test_connection.py` can optionally run against a remote server by setting `HOP3_DEV_HOST`:

```bash
export HOP3_DEV_HOST=hop3@test-server.example.com
pytest packages/hop3-server/tests/c_system/test_connection.py -v
```

⚠️ **This is ONLY for diagnosing issues with actual remote servers, NOT for regular testing!**

Remote server requirements (if used):
- ✅ Authentication enabled (`HOP3_ENABLE_AUTH=true`)
- ✅ Secret key configured (`HOP3_SECRET_KEY`)
- ✅ Database initialized
- ❌ **Not needed**: nginx, uwsgi, systemd (those are for E2E tests in `d_e2e/`)


## Future Enhancements

- [ ] Add comprehensive auth flow tests (register, login, logout, whoami)
- [ ] Add app management command tests (without deployment)
- [ ] Add service command tests
- [ ] Add config command tests
- [ ] Add error handling tests
- [ ] Add concurrent test execution support
