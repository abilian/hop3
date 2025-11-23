# Hop3 Testing Strategy

## Overview

Hop3 uses a comprehensive four-layer testing pyramid to ensure code quality, reliability, and security. This document describes the testing strategy, best practices, and guidelines for writing and running tests.

## The Testing Pyramid

```
           /\
          /  \  E2E Tests (d_e2e/)
         /    \  - Slowest, most comprehensive
        /------\  - Real deployments in Docker
       /        \
      /  System  \ System Tests (c_system/)
     /   Tests    \ - Docker-based CLI ↔ Server tests
    /--------------\ - Isolated, reproducible
   /                \
  /   Integration    \ Integration Tests (b_integration/)
 /      Tests         \ - Component interactions
/______________________\ - In-memory database

   Unit Tests (a_unit/)
   - Fastest, most isolated
   - Mock all dependencies
```

### Test Layer Characteristics

| Layer | Speed | Scope | Dependencies | When to Run |
|-------|-------|-------|--------------|-------------|
| Unit | < 1s | Individual functions/classes | None (mocked) | Every save |
| Integration | ~10s | Multiple components | In-memory DB | Before commit |
| System | ~20s | CLI ↔ Server | Docker | Before push |
| E2E | 10-20min | Complete workflows | Docker + apps | CI/CD |

## Layer 1: Unit Tests

**Location**: `packages/hop3-server/tests/a_unit/`

**Purpose**: Test individual functions and classes in complete isolation.

**Characteristics**:
- Very fast execution (< 1 second total)
- No external dependencies (uses in-memory SQLite for database)
- Test business logic and service behavior
- Use dependency injection fixtures for services

**Example**:
```python
def test_app_name_validation():
    """Test that app names must be valid identifiers."""
    assert is_valid_app_name("my-app")
    assert not is_valid_app_name("my app")  # spaces not allowed
    assert not is_valid_app_name("123app")  # can't start with number

def test_backup_manager(di_container):
    """Test BackupManager with DI container."""
    with di_container() as request_container:
        manager = request_container.get(BackupManager)
        assert isinstance(manager, BackupManager)
```

**Running**:
```bash
pytest packages/hop3-server/tests/a_unit/ -v
```

### Dependency Injection Testing

Unit tests extensively use Hop3's Dishka DI system. See the [DI Testing Guide](di-testing-guide.md) for detailed patterns and best practices.

**Key Principles**:
- Use real services with in-memory database (not mocks)
- Use pytest fixtures for container management
- Use `di_container` fixture for core services
- Use `create_container()` fixture for plugin services
- No environment manipulation in tests (use `autouse` fixtures)
- No unnecessary try/finally blocks (use fixtures)

## Layer 2: Integration Tests

**Location**: `packages/hop3-server/tests/b_integration/`

**Purpose**: Test multiple components working together within subsystems.

**Characteristics**:
- Fast execution (~10 seconds)
- Uses real database (in-memory SQLite)
- Uses Starlette TestClient for HTTP
- No external network dependencies
- Tests component interactions

**Coverage**:
- Authentication commands (register, login, whoami, logout)
- RPC endpoint security
- Command authentication and authorization
- Database operations

**Example**:
```python
def test_auth_login_flow(client, db):
    """Test complete login flow with JWT token generation."""
    # Register user
    response = client.post("/rpc", json={
        "method": "auth:register",
        "params": {"username": "test", "password": "secret123"}
    })
    assert response.status_code == 200

    # Login
    response = client.post("/rpc", json={
        "method": "auth:login",
        "params": {"username": "test", "password": "secret123"}
    })
    assert response.status_code == 200
    token = response.json()["result"]["token"]
    assert token
```

**Running**:
```bash
pytest packages/hop3-server/tests/b_integration/ -v
```

## Layer 3: System Tests

**Location**: `packages/hop3-server/tests/c_system/`

**Purpose**: Test the full application with real dependencies in Docker containers.

**Characteristics**:
- Medium execution time (~20 seconds after initial image build)
- Uses Docker containers (`hop3-e2e:test` image)
- Real hop3-server running in container
- HTTP-based CLI communication
- Isolated, reproducible environment

**Coverage**:
- CLI availability and basic functionality
- Authentication commands
- App deployment via tarball
- App lifecycle (deploy, list, destroy)
- Git hook deployment

### Docker-Based Testing Infrastructure

System tests automatically use Docker to provide an isolated, reproducible test environment:

```bash
# Tests automatically:
# 1. Build hop3-e2e:test Docker image (if needed)
# 2. Start container with hop3-server
# 3. Wait for server to be ready
# 4. Run tests against container
# 5. Clean up container

pytest packages/hop3-server/tests/c_system/ -v
```

The Docker image includes:
- Complete hop3-server installation
- SQLite database
- Supervisor for process management
- SSH and HTTP access
- Test applications

**Important**: Ensure `HOP3_DEV_HOST` is **not set** for Docker-based testing:
```bash
unset HOP3_DEV_HOST
pytest packages/hop3-server/tests/c_system/ -v
```

### HOP3_UNSAFE Mode

For simplified testing in Docker environments, system and E2E tests use `HOP3_UNSAFE` mode to bypass authentication.

**Configuration**:

The Docker container is configured with:
```bash
# In .env file
HOP3_UNSAFE=true
```

Or in `hop3-server.toml`:
```toml
[security]
unsafe = true
```

**What HOP3_UNSAFE Does**:

When `HOP3_UNSAFE=true`:
1. Authentication middleware returns a mock admin user for all requests
2. RPC handler skips authentication checks
3. All commands are accessible without tokens
4. All requests are treated as authenticated admin users

**Security Warning**:

⚠️ **CRITICAL SECURITY WARNING** ⚠️

`HOP3_UNSAFE` completely disables authentication and authorization. This mode:
- Must **NEVER** be used in production
- Must **ONLY** be used in isolated test environments
- Should **ONLY** be enabled in Docker containers used for testing
- Grants **full admin access** to anyone who can reach the server

The middleware includes explicit checks:
```python
# In middleware/auth.py
if config.HOP3_UNSAFE:
    # WARNING: This should ONLY be used in testing environments
    return AuthCredentials(["authenticated", "admin"]), SimpleUser("unsafe-test-user")
```

**Verifying HOP3_UNSAFE is Disabled**:

Before deploying to production, always verify:
```bash
# Check environment
echo $HOP3_UNSAFE  # Should be empty or "false"

# Check config file
grep -i unsafe /etc/hop3/hop3-server.toml  # Should not exist or be false

# Check running server
curl http://localhost:8080/health  # Should require authentication
```

### Remote Server Diagnostics (Optional)

Some tests can optionally run against a remote server for diagnostics:
```bash
# Only for remote server diagnostics
export HOP3_DEV_HOST=hop3@test-server.example.com
pytest packages/hop3-server/tests/c_system/test_connection.py -v
```

This is **not** part of the standard test suite and is only for testing actual remote deployments.

**Running**:
```bash
# Standard Docker-based tests
pytest packages/hop3-server/tests/c_system/ -v

# With verbose output
pytest packages/hop3-server/tests/c_system/ -v -s
```

## Layer 4: E2E Tests

**Location**: `packages/hop3-server/tests/d_e2e/`

**Purpose**: Test complete workflows in production-like Docker environment.

**Characteristics**:
- Slow execution (10-20 minutes, includes image build)
- Docker containers with supervisor
- Full hop3 stack (server, SSH, HTTP, apps)
- Real deployment workflows
- `HOP3_UNSAFE=true` configured in Dockerfile

**Coverage**:
- Python Flask/Django app deployment
- Full deployment lifecycle
- HTTP endpoint verification
- Git hook deployment
- Security tests

**Infrastructure**:

E2E tests use a comprehensive Docker setup:
- `hop3-e2e:test` image with full installation
- Supervisor for process management (not systemd)
- Real nginx/caddy/traefik proxy
- Real application deployments
- Network isolation

**Running**:
```bash
# Install Docker requirements
pip install -r packages/hop3-server/tests/d_e2e/requirements.txt

# Run E2E tests
pytest packages/hop3-server/tests/d_e2e/ -v

# Run specific test
pytest packages/hop3-server/tests/d_e2e/test_flask_app.py -v
```

### E2E Test Suite Consolidation

**Status**: As of October 2025, Hop3 is consolidating its E2E test suites to reduce duplication and improve testing efficiency.

**Two E2E Frameworks**:

1. **`packages/hop3-testing/tests/`** (Legacy Framework)
   - Uses DeploymentTarget abstraction
   - Supports Docker and remote server targets
   - **Status**: Deprecated for E2E testing, preserved as library

2. **`packages/hop3-server/tests/d_e2e/`** (Modern Framework)
   - Docker-focused with comprehensive fixtures
   - Better infrastructure and cleanup
   - Includes proxy plugin testing
   - **Status**: Primary E2E test suite

**Migration Status**:

The following tests have been deprecated and migrated to d_e2e:
- `test_deploy_basic_app()` → `test_python_deployment.py` and `test_full_deployment.py`
- `test_deploy_all_simple_apps()` → `test_full_deployment.py`
- `test_static_app_deployment()` → `test_static_deployment.py`
- `test_flask_app_deployment()` → `test_python_deployment.py` and `test_full_deployment.py`

Tests in `packages/hop3-testing/tests/test_basic_apps.py` are now marked as skipped with references to their d_e2e equivalents.

**Benefits**:
- 20-40% reduction in E2E test execution time
- Single, consistent E2E framework
- Clearer test organization
- Easier maintenance

**For Details**: See `local-notes/TEST-SUITE-CONSOLIDATION.md` for complete analysis and migration plan.

## Best Practices

### Writing Tests

1. **Follow the test pyramid**: More unit tests, fewer E2E tests
2. **Test one thing**: Each test should verify one behavior
3. **Use descriptive names**: `test_user_cannot_delete_other_users_apps()`
4. **Arrange-Act-Assert**: Structure tests clearly
5. **Avoid test interdependence**: Tests should be independent and order-agnostic

### Test Naming Conventions

```python
# Good
def test_app_deployment_creates_virtual_host():
    """Test that deploying an app creates nginx virtual host."""

# Bad
def test1():
    """Test stuff."""
```

### Fixtures

Use pytest fixtures for common setup:

```python
@pytest.fixture
def sample_app(tmp_path):
    """Create a sample app directory for testing."""
    app_dir = tmp_path / "test-app"
    app_dir.mkdir()
    (app_dir / "Procfile").write_text("web: gunicorn app:app")
    return app_dir
```

### Parametrized Tests

Use parametrization for testing multiple cases:

```python
@pytest.mark.parametrize("app_name,valid", [
    ("my-app", True),
    ("my_app", True),
    ("my app", False),
    ("123app", False),
])
def test_app_name_validation(app_name, valid):
    """Test app name validation rules."""
    assert is_valid_app_name(app_name) == valid
```

### Mocking

Use mocking appropriately in unit tests:

```python
from unittest.mock import patch, MagicMock

def test_deploy_calls_git_clone():
    """Test that deploy() calls git clone."""
    with patch('subprocess.run') as mock_run:
        deploy_from_git("https://github.com/user/repo.git")
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert "git" in args
        assert "clone" in args
```

## Running Tests

### Quick Commands

```bash
# All tests (unit + integration only)
pytest

# All tests including system/E2E
pytest packages/hop3-server/tests/

# Specific layer
pytest packages/hop3-server/tests/a_unit/
pytest packages/hop3-server/tests/b_integration/
pytest packages/hop3-server/tests/c_system/
pytest packages/hop3-server/tests/d_e2e/

# Specific test file
pytest packages/hop3-server/tests/a_unit/test_app.py

# Specific test
pytest packages/hop3-server/tests/a_unit/test_app.py::test_app_name_validation

# With coverage
pytest --cov=hop3 --cov-report=html

# Verbose output
pytest -v

# Show print statements
pytest -v -s

# Stop on first failure
pytest -x

# Run last failed tests
pytest --lf
```

### Environment Setup

```bash
# Install dependencies
uv sync

# Install test dependencies
uv sync --dev

# Ensure HOP3_DEV_HOST is not set (for Docker tests)
unset HOP3_DEV_HOST

# Set up test database (if needed)
export HOP3_DB_URL=sqlite:///:memory:
```

## Continuous Integration

### Pre-commit Checks

Before committing:
```bash
# Run fast tests
pytest packages/hop3-server/tests/a_unit/ packages/hop3-server/tests/b_integration/

# Run linting
make lint

# Run type checking
make typecheck
```

### Pre-push Checks

Before pushing:
```bash
# Run system tests
pytest packages/hop3-server/tests/c_system/

# Run all tests
make test
```

### CI/CD Pipeline

Recommended CI/CD stages:

1. **Fast Feedback** (every commit):
   - Unit tests
   - Integration tests
   - Linting
   - Type checking

2. **Medium Checks** (every push):
   - System tests (Docker)
   - Code coverage
   - Security scans

3. **Full Validation** (scheduled/release):
   - E2E tests
   - Performance tests
   - Security audits

## Coverage Targets

| Component | Target | Current |
|-----------|--------|---------|
| Overall | > 75% | ~70% |
| Core modules | > 85% | ~80% |
| Commands | > 90% | ~85% |
| Plugins | > 70% | ~65% |

View coverage:
```bash
pytest --cov=hop3 --cov-report=html
open htmlcov/index.html
```

## Troubleshooting

### Tests Hang

- Check Docker daemon is running
- Check for background processes
- Use `-v -s` to see progress
- Check logs: `docker logs <container-id>`

### Import Errors

```bash
# Reinstall dependencies
uv sync

# Check PYTHONPATH
echo $PYTHONPATH

# Install in editable mode
uv pip install -e packages/hop3-server/
```

### Database Errors

- Unit/integration tests use in-memory SQLite (no setup needed)
- System/E2E tests use SQLite in Docker (automatic)
- Check database file permissions

### Docker Issues

```bash
# Check Docker is running
docker ps

# Rebuild test image
docker build -f packages/hop3-server/tests/d_e2e/docker/Dockerfile -t hop3-e2e:test .

# Clean up containers
docker ps -a | grep hop3 | awk '{print $1}' | xargs docker rm -f

# Check container logs
docker logs <container-id>
```

### Authentication Issues in Tests

If tests fail with authentication errors:

1. **For Docker tests**: Verify `HOP3_UNSAFE=true` is set in Dockerfile
2. **For remote tests**: Ensure you have valid token in `~/.config/hop3-cli/config.toml`
3. **Check environment**: `env | grep HOP3`

## Security Testing

### Testing Authentication

```python
def test_unauthenticated_request_fails():
    """Test that requests without auth token are rejected."""
    response = client.post("/rpc", json={"method": "app:list"})
    assert response.status_code == 401
```

### Testing Authorization

```python
def test_non_admin_cannot_create_users():
    """Test that non-admin users cannot create users."""
    # Login as regular user
    token = login_as_user("regular-user")

    # Try to create user
    response = client.post(
        "/rpc",
        headers={"Authorization": f"Bearer {token}"},
        json={"method": "admin:user:add", "params": {"username": "new-user"}}
    )
    assert response.status_code == 403
```

### Testing Input Validation

```python
def test_sql_injection_prevented():
    """Test that SQL injection attempts are prevented."""
    response = client.post("/rpc", json={
        "method": "app:list",
        "params": {"name": "'; DROP TABLE apps; --"}
    })
    # Should not cause error, should return empty result
    assert response.status_code == 200
```

## Performance Testing

### Load Testing (Future)

```bash
# Using locust
locust -f tests/load/locustfile.py

# Using hey
hey -n 1000 -c 10 http://localhost:8080/health
```

### Resource Monitoring

```bash
# Monitor during tests
docker stats

# Check memory usage
pytest --memray
```

## Future Improvements

1. **Coverage**: Increase overall coverage to 80%+
2. **Performance**: Add benchmark tests
3. **Chaos**: Add chaos engineering tests
4. **Security**: Add automated security scanning
5. **Load**: Add load testing suite
6. **Mutation**: Add mutation testing

## References

- [DI Testing Guide](di-testing-guide.md) - Dependency injection testing patterns and best practices
- [TEST-STATUS.md](/notes/test-status.md) - Current test status
- [PROJECT-STATUS.md](/notes/current-status.md) - Overall project status
- [ADR 092](/notes/adrs/092-pluggy-dishka-integration.md) - Pluggy+Dishka integration architecture
- [pytest documentation](https://docs.pytest.org/)
- [Dishka documentation](https://dishka.readthedocs.io/)
- [Testing Best Practices](https://testdriven.io/blog/testing-best-practices/)
