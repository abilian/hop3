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

1. **hop3-cli binary** must be installed and available in PATH:
   ```bash
   pip install -e packages/hop3-cli
   ```

2. **hop3-server** - Three options:

   **Option A: Automatic Local Server (Default - Recommended)**
   ```bash
   # No setup needed! Tests will automatically:
   # - Start a server in /tmp/hop3-system-test-XXXXX/
   # - Configure authentication
   # - Clean up after tests complete

   pytest packages/hop3-server/tests/c_system/
   ```

   **Option B: Manual Local Server (Development)**
   ```bash
   # Terminal 1: Start server
   hop-server serve

   # Terminal 2: Run tests
   export HOP3_API_URL=http://localhost:8000
   pytest packages/hop3-server/tests/c_system/
   ```

   **Option C: Remote Server (CI/Production Testing)**
   ```bash
   export HOP3_DEV_HOST=hop3@test-server.example.com
   pytest packages/hop3-server/tests/c_system/
   ```

   **Option D: Full Infrastructure Testing (Production-like)**
   ```bash
   # Server must have uwsgi, nginx, systemd fully configured
   export HOP3_DEV_HOST=hop3@production-test-server.example.com
   export HOP3_FULL_INFRASTRUCTURE=true
   pytest packages/hop3-server/tests/c_system/
   ```

## Running System Integration Tests

### Recommended: Automatic local server (no setup needed)
```bash
# Just run the tests - server starts automatically!
pytest packages/hop3-server/tests/c_system/ -v -s

# Less verbose
pytest packages/hop3-server/tests/c_system/

# Run specific test
pytest packages/hop3-server/tests/c_system/test_connection.py -v
```

The tests will:
1. Automatically start a server in `/tmp/hop3-system-test-XXXXX/`
2. Wait for it to be ready
3. Run all tests
4. Stop and clean up the server

### Optional: Test connection to remote server
```bash
# For remote server testing, run diagnostic script first
export HOP3_DEV_HOST=hop3@test-server.example.com
python packages/hop3-server/tests/c_system/test_connection.py
```

This will check:
- SSH connectivity to server
- hop3-cli installation
- Server responsiveness

### Skip system tests (run only unit and integration):
```bash
pytest packages/hop3-server/tests/a_unit packages/hop3-server/tests/b_integration
```

## Test Structure

### `conftest.py`
Provides pytest fixtures for system integration testing:
- `local_server`: Automatically starts/stops a server in /tmp (session scope)
- `e2e_enabled`: Checks if system tests can run (uses local or remote server)
- `hop3_config_dir`: Creates temporary config directory and sets HOP3_API_URL
- `system_auth_token`: Registers test user and gets authentication token
- `test_app_dir`: Creates temporary directory for test data
- `deployed_app`: Manages app deployment lifecycle and cleanup
- `hop3()`: Helper function to run hop3-cli commands
- `requires_full_infrastructure`: Skip marker for tests requiring uwsgi/nginx/systemd
- `remote_server_only`: Skip marker for remote server diagnostic tests

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
| **Server** | TestClient (no process) | Real server process | Real server + system |
| **CLI** | Direct function calls | Real hop3-cli binary | Real hop3-cli binary |
| **Network** | In-memory | Real HTTP/SSH | Real HTTP/SSH |
| **Deployments** | Mocked | No deployments | Real deployments |
| **Speed** | Very fast (<1s) | Fast (2-5s) | Slow (30-60s) |
| **Isolation** | Complete | Shared server | Complete (container) |

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

1. **Check if server is running**:
   ```bash
   # For local server
   curl http://localhost:8000/health

   # For remote server
   ssh hop3@your-server.com "systemctl status hop3-server"
   ```

2. **Check environment variables**:
   ```bash
   echo $HOP3_API_URL
   echo $HOP3_DEV_HOST
   ```

3. **Run diagnostic script**:
   ```bash
   python packages/hop3-server/tests/c_system/test_connection.py
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
# Using local server
export HOP3_API_URL="http://localhost:8000"
hop3 auth:register testuser test@example.com testpassword
hop3 auth:login testuser testpassword
hop3 apps

# Using SSH tunnel (remote server)
export HOP3_API_URL="ssh://hop3@your-server.com"
hop3 auth:login testuser testpassword
hop3 apps
```

### Check server logs:
```bash
# Local server (if using hop-server serve)
# Check terminal output

# Remote server
ssh hop3@dev.example.com
sudo journalctl -u hop3-server -f
```

### Common timeout causes:

- **"Registering test user" timeout**: Server not responding or auth disabled
- **"Logging in" timeout**: Server not responding, wrong credentials, or missing HOP3_SECRET_KEY
- **"Running: hop3 apps" timeout**: Token not set or invalid

## CI Integration

System integration tests are designed for CI and require **no manual server setup**!

Example GitHub Actions workflow:
```yaml
- name: Run system integration tests
  run: |
    # Tests automatically start and stop server
    pytest packages/hop3-server/tests/c_system/ -v
```

For testing against a specific server (optional):
```yaml
- name: Run system integration tests against dev server
  env:
    HOP3_DEV_HOST: hop3@dev.example.com
  run: |
    pytest packages/hop3-server/tests/c_system/ -v
```

## Server Setup Requirements

### Automatic local server (default)
**No setup required!** The test fixtures automatically:
- Create a temporary directory in `/tmp/hop3-system-test-XXXXX/`
- Enable authentication with a test secret key
- Initialize the database
- Start the server
- Clean up after tests

### Remote server (HOP3_DEV_HOST)
If using a remote server for basic tests, it must have:
- ✅ Authentication enabled (`HOP3_ENABLE_AUTH=true`)
- ✅ Secret key configured (`HOP3_SECRET_KEY`)
- ✅ Database initialized
- ❌ No need for nginx (unless `HOP3_FULL_INFRASTRUCTURE=true`)
- ❌ No need for uwsgi (unless `HOP3_FULL_INFRASTRUCTURE=true`)
- ❌ No need for systemd (unless `HOP3_FULL_INFRASTRUCTURE=true`)

### Full infrastructure server (HOP3_FULL_INFRASTRUCTURE=true)
If running full deployment tests, the server needs:
- ✅ All of the above (auth, secret key, database)
- ✅ nginx configured and running
- ✅ uwsgi configured for application deployments
- ✅ systemd for service management
- ✅ Full deployment pipeline working


## Future Enhancements

- [ ] Add comprehensive auth flow tests (register, login, logout, whoami)
- [ ] Add app management command tests (without deployment)
- [ ] Add service command tests
- [ ] Add config command tests
- [ ] Add error handling tests
- [ ] Add concurrent test execution support
