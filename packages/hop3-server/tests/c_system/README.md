# System Integration Tests

This directory contains system integration tests that verify hop3-cli and hop3-server work together correctly, including authentication, RPC communication, and basic command execution.

**Important**: These are **not** full end-to-end tests with actual application deployments. For full E2E tests, see `tests/d_e2e/`.

## Test Scope

System integration tests verify:
- ✅ CLI ↔ Server RPC communication
- ✅ Authentication flow (register, login, token validation)
- ✅ All CLI commands execute successfully
- ✅ Service management commands (without actual deployments)
- ❌ No actual application deployments
- ❌ No nginx/uwsgi configuration
- ❌ No systemd services

## Requirements

1. **hop3-cli binary** must be installed and available in PATH:
   ```bash
   pip install -e packages/hop3-cli
   ```

2. **hop3-server** must be running. Two options:

   **Option A: Local Server (Development)**
   ```bash
   # Terminal 1: Start server
   hop-server serve

   # Terminal 2: Run tests
   export HOP3_API_URL=http://localhost:8000
   pytest tests/c_system/
   ```

   **Option B: Remote Server (CI)**
   ```bash
   export HOP3_DEV_HOST=hop3@test-server.example.com
   pytest tests/c_system/
   ```

3. **Server configuration** (if not using defaults):
   ```bash
   export HOP3_ENABLE_AUTH=true
   export HOP3_SECRET_KEY="your-secret-key"
   ```

## Running System Integration Tests

### First, test your connection:
```bash
# Run diagnostic script to verify setup
python packages/hop3-server/tests/c_system/test_connection.py
```

This will check:
- SSH connectivity to server (if using HOP3_DEV_HOST)
- HTTP connectivity to server (if using HOP3_API_URL)
- hop3-cli installation
- Server responsiveness

### Run all system tests:
```bash
# With verbose output
pytest packages/hop3-server/tests/c_system/ -v -s

# Less verbose
pytest packages/hop3-server/tests/c_system/
```

### Run specific test:
```bash
pytest packages/hop3-server/tests/c_system/test_connection.py -v
```

### Skip system tests (run only unit and integration):
```bash
pytest packages/hop3-server/tests/a_unit packages/hop3-server/tests/b_integration
```

## Test Structure

### `conftest.py`
Provides pytest fixtures for system integration testing:
- `system_enabled`: Checks if system tests can run (server available)
- `hop3_config_dir`: Creates temporary config directory
- `system_auth_token`: Registers test user and gets authentication token
- `test_app_dir`: Creates temporary directory for test data
- `hop3()`: Helper function to run hop3-cli commands

### `test_connection.py`
Diagnostic tests to verify system setup:
- SSH connectivity
- HTTP connectivity
- CLI availability
- Server responsiveness
- Authentication commands available

### `test_auth_flow.py` (future)
Tests authentication flow end-to-end:
- User registration via `hop3 auth:register`
- Login via `hop3 auth:login`
- Token validation
- Logout via `hop3 auth:logout`

### `test_app_management.py` (future)
Tests app management commands (without actual deployment):
- `hop3 apps` - list apps
- `hop3 status <app>` - check app status
- App name validation
- Error handling

### `test_service_commands.py` (future)
Tests service management commands:
- `hop3 services:list`
- `hop3 services:create postgres <name>`
- `hop3 services:info <service>`
- `hop3 services:destroy <service>`

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

System integration tests are designed for CI with:
1. Server started in background: `hop-server serve &`
2. Wait for server to be ready: `sleep 5`
3. Set HOP3_API_URL to localhost
4. Run tests: `pytest tests/c_system/`

Example GitHub Actions workflow:
```yaml
- name: Start hop3-server
  run: |
    hop-server serve &
    sleep 5

- name: Run system integration tests
  run: |
    export HOP3_API_URL=http://localhost:8000
    pytest tests/c_system/ -v
```

## Server Setup Requirements

System tests require the server to have:
- ✅ Authentication enabled (`HOP3_ENABLE_AUTH=true`)
- ✅ Secret key configured (`HOP3_SECRET_KEY`)
- ✅ Database initialized
- ❌ No need for nginx
- ❌ No need for uwsgi
- ❌ No need for systemd
- ❌ No need for actual deployment capabilities

## Migration from c_e2e

These tests were previously in `tests/c_e2e/` but were renamed to `c_system/` to better reflect their scope:

- **Old name**: "End-to-End Tests" (c_e2e)
- **New name**: "System Integration Tests" (c_system)
- **Reason**: These tests don't deploy applications, so they're not true E2E tests

True end-to-end tests with actual deployments are now in `tests/d_e2e/`.

## Future Enhancements

- [ ] Add comprehensive auth flow tests (register, login, logout, whoami)
- [ ] Add app management command tests (without deployment)
- [ ] Add service command tests
- [ ] Add config command tests
- [ ] Add error handling tests
- [ ] Add concurrent test execution support
