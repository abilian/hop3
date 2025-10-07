# End-to-End Tests Using hop3-cli

This directory contains end-to-end tests that use the `hop3-cli` binary to test the full deployment workflow with authentication.

## Requirements

1. **hop3-cli binary** must be installed and available in PATH:
   ```bash
   pip install -e packages/hop3-cli
   ```

2. **HOP3_DEV_HOST** environment variable must be set to your test server:
   ```bash
   export HOP3_DEV_HOST="hop3@dev.example.com"
   ```

3. **Server must be running** with authentication enabled:
   ```bash
   export HOP3_ENABLE_AUTH=true
   export HOP3_SECRET_KEY="your-secret-key"
   ```

## Running E2E Tests

### First, test your connection:
```bash
# Run diagnostic script to verify setup
python packages/hop3-server/tests/c_e2e/test_connection.py
```

This will check:
- SSH connectivity to server
- hop3-cli installation
- hop3-cli can connect via SSH tunnel

### Run all E2E tests:
```bash
# With verbose output to see progress
pytest packages/hop3-server/tests/c_e2e/ -v -s

# Or less verbose
pytest packages/hop3-server/tests/c_e2e/
```

### Run specific test class:
```bash
pytest packages/hop3-server/tests/c_e2e/test_e2e_deployment.py::TestTarballDeployment
```

### Run with verbose output:
```bash
pytest packages/hop3-server/tests/c_e2e/ -v -s
```

### Skip E2E tests (run unit and integration tests only):
```bash
pytest packages/hop3-server/tests/a_unit packages/hop3-server/tests/b_integration
```

## Test Structure

### `conftest.py`
Provides pytest fixtures for E2E testing:
- `e2e_enabled`: Checks if E2E tests can run (HOP3_DEV_HOST set)
- `hop3_config_dir`: Creates temporary config directory
- `e2e_auth_token`: Registers test user and gets authentication token
- `test_app_dir`: Creates temporary directory for test apps
- `deployed_app`: Fixture that deploys an app and cleans it up after test
- `hop3()`: Helper function to run hop3-cli commands
- `create_simple_flask_app()`: Helper to create test Flask apps

### `test_e2e_deployment.py`
Tests for tarball deployment and application lifecycle:
- **TestTarballDeployment**: Deploy apps via `hop3 deploy`
- **TestApplicationLifecycle**: Start, stop, restart, status commands
- **TestEnvironmentVariables**: Config management
- **TestApplicationDestruction**: App cleanup
- **TestAuthentication**: Verify auth requirements
- **TestAppsList**: List deployed apps
- **TestWebEndpoint**: HTTP accessibility

### `test_e2e_git_hook.py`
Tests for git-hook deployment method:
- **TestGitHookDeployment**: Deploy via git-hook command
- **TestGitHookSecurity**: Security tests for git-hook

## Key Differences from Legacy E2E Tests

| Aspect | Legacy Tests | New E2E Tests |
|--------|--------------|---------------|
| CLI | Direct SSH commands | hop3-cli binary |
| Deployment | `git push` only | `hop3 deploy` (tarball) + git-hook |
| Authentication | SSH keys only | JWT tokens via auth:login |
| Test Runner | Custom `hop-test` | Standard pytest |
| Fixtures | Manual setup/cleanup | pytest fixtures |
| Config | SSH config | Environment variables (HOP3_API_URL, HOP3_API_TOKEN) |

## Authentication Flow

1. **Session setup**: Test user is registered via `hop3 auth:register`
2. **Login**: Token obtained via `hop3 auth:login`
3. **Config**: Token set via `HOP3_API_TOKEN` environment variable
4. **All commands**: Use Bearer token authentication automatically
5. **Cleanup**: Logout via `hop3 auth:logout` at end of session

The tests use environment variables (`HOP3_API_URL` and `HOP3_API_TOKEN`) instead of config files for reliability.

## Debugging

### Tests hanging or timing out?

If tests hang for more than 30 seconds, it's usually one of these issues:

1. **SSH connection problem**: Run the diagnostic script first:
   ```bash
   python packages/hop3-server/tests/c_e2e/test_connection.py
   ```

2. **SSH keys not set up**: Make sure you can SSH without password:
   ```bash
   ssh hop3@your-server.com
   ```

3. **Server not responding**: Check if server is running

4. **Firewall blocking**: Check firewall rules on server

### Verbose test output

Always run with `-s` flag to see progress:
```bash
pytest packages/hop3-server/tests/c_e2e/ -v -s --tb=short -x
```

Flags explained:
- `-v`: Verbose test names
- `-s`: Show print statements (progress indicators)
- `--tb=short`: Short tracebacks
- `-x`: Stop on first failure

### Check environment configuration:
```bash
echo $HOP3_DEV_HOST
echo $HOP3_API_URL
echo $HOP3_API_TOKEN
```

### Test authentication manually:
```bash
export HOP3_API_URL="ssh://hop3@your-server.com"
hop3 auth:login testuser testpassword
hop3 apps
```

### Run single test with output:
```bash
pytest packages/hop3-server/tests/c_e2e/test_e2e_deployment.py::TestTarballDeployment::test_deploy_simple_flask_app -v -s
```

### Check server logs:
```bash
ssh hop3@dev.example.com
tail -f /var/log/hop3/server.log
```

### Common timeouts and their meanings:

- **Timeout at "Registering test user"**: SSH tunnel setup issue
- **Timeout at "Logging in"**: Server not responding or auth disabled
- **Timeout at "Running: hop3 deploy"**: Large file upload or slow network

## CI Integration

These tests are designed to run in CI with:
1. A test server provisioned in CI environment
2. HOP3_DEV_HOST set to the test server
3. Authentication enabled on the server
4. hop3-cli binary installed

See `.github/workflows/e2e-tests.yml` for CI configuration.

## Known Limitations

1. **Git-hook tests**: Full git push workflow tests require more complex setup (git remote push to server)
2. **Web endpoint tests**: Require DNS/host configuration for `{app}.{domain}`
3. **Service tests**: Database service tests not yet included (future work)
4. **Parallel execution**: Tests should run sequentially to avoid app name conflicts

## Future Enhancements

- [ ] Add tests for service attachment (PostgreSQL)
- [ ] Add tests for backup/restore functionality
- [ ] Add tests for log streaming
- [ ] Add tests for scaling/worker management
- [ ] Add full git push workflow test
- [ ] Add parallel test execution with unique app names
