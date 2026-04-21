# Testing Strategy

This document outlines Hop3's comprehensive testing strategy, covering unit tests, integration tests, system integration tests, and full end-to-end tests.

**Last Updated**: 2026-02-17

## Overview

Hop3 uses a four-layer testing pyramid plus a unified test runner (`hop3-test`) to ensure code quality, catch regressions early, and validate complete system behavior.

```
                    ▲
                   ╱│╲
                  ╱ │ ╲
                 ╱  │  ╲
                ╱   │   ╲    Layer 4: Full E2E Tests (d_e2e/)
               ╱────┼────╲   Real deployments, nginx, uWSGI
              ╱     │     ╲  ~17 tests, 10-20 min
             ╱──────┼──────╲
            ╱       │       ╲
           ╱────────┼────────╲  Layer 3: System Integration (c_system/)
          ╱         │         ╲ Dashboard + Docker
         ╱──────────┼──────────╲ ~13 tests, 30s-2 min
        ╱           │           ╲
       ╱────────────┼────────────╲  Layer 2: Integration Tests (b_integration/)
      ╱             │             ╲ Multiple components, no external deps
     ╱──────────────┼──────────────╲ ~247 tests, 10-30 sec
    ╱               │               ╲
   ╱────────────────┼────────────────╲  Layer 1: Unit Tests (a_unit/)
  ╱_________________│_________________╲ Individual components
 ╱_____________________________________╲ ~361 tests, 5-10 sec
```

## Layer 1: Unit Tests (`tests/a_unit/`)

### Purpose
Test individual functions, classes, and modules in complete isolation.

### Characteristics
- Fast execution (< 1ms per test)
- No external dependencies
- Use mocks and fakes liberally
- Test edge cases and error conditions
- No database connections
- No file I/O (use temp directories or mocks)
- No network calls

### Structure
```
tests/a_unit/
├── commands/          # Command classes
├── orm/               # Database models (using in-memory SQLite)
├── server/            # Server components
├── plugins/           # Plugin implementations
├── uwsgi/             # uWSGI settings
└── test_*.py          # Miscellaneous unit tests
```

### Example
```python
# tests/a_unit/test_archives.py


def test_is_safe_filename_rejects_path_traversal():
    """Test that path traversal attempts are rejected."""
    assert not is_safe_filename("../etc/passwd")
    assert not is_safe_filename("foo/../../etc/passwd")


def test_is_safe_filename_accepts_normal_paths():
    """Test that normal filenames are accepted."""
    assert is_safe_filename("foo.txt")
    assert is_safe_filename("dir/foo.txt")
```

### Current Status
**361 tests passing**

### Guidelines
- Each test should complete in < 10ms
- Aim for > 80% code coverage
- Test both success and failure paths
- Use descriptive test names: `test_<action>_<expected_result>`

---

## Layer 2: Integration Tests (`tests/b_integration/`)

### Purpose
Test how multiple components work together within a subsystem, without requiring external infrastructure.

### Characteristics
- Use Litestar TestClient (no real server process)
- Use in-memory or temporary databases
- Use temporary file systems
- Test interactions between 2-5 components
- No SSH connections
- No real Linux system operations
- No deployed applications

### Structure
```
tests/b_integration/
├── test_rpc_auth.py            # RPC + Auth guard
├── test_rpc_security.py        # RPC + Security
├── test_dashboard_*.py         # Dashboard views
├── test_services_commands_*.py # Service commands
└── test_deployment_flow.py     # Deployer + Builder (temp dirs)
```

### Example
```python
# tests/b_integration/test_rpc_security.py


def test_authenticated_command_requires_token(client: TestClient):
    """Test that authenticated commands reject requests without tokens."""
    response = client.post(
        "/rpc",
        json={
            "jsonrpc": "2.0",
            "method": "cli",
            "params": {"cli_args": ["apps"], "extra_args": {}},
            "id": 1,
        },
    )

    assert response.status_code == 401
    data = response.json()
    assert "Authentication required" in data["error"]["message"]
```

### Current Status
**247 tests passing**

### Guidelines
- Each test should complete in < 1 second
- Use TestClient instead of real HTTP requests
- Use temporary directories for file operations
- Mock external services (nginx, systemd)
- Test failure scenarios and error handling

---

## Layer 3: System Integration Tests (`tests/c_system/`)

### Purpose
Test the full application with real dependencies in Docker, focusing on dashboard and CLI interactions.

### Characteristics
- Real hop3-server process (in Docker)
- Real HTTP communication
- Real database operations
- `HOP3_UNSAFE=true` for test authentication bypass
- No actual app deployments (that's Layer 4)
- No nginx/uWSGI configuration

### Structure
```
tests/c_system/
├── conftest.py                  # Docker fixtures
├── test_dashboard_app_*.py      # Dashboard app management
└── test_connection.py           # Basic connectivity
```

### Current Status
**13 tests passing**

### Guidelines
- Tests should use real HTTP requests
- Clean up created resources in fixtures
- Use unique names (timestamps) to avoid conflicts
- Each test should complete in < 5 seconds

---

## Layer 4: Full End-to-End Tests (`tests/d_e2e/`)

### Purpose
Test the complete system including actual application deployments, web server configuration, and HTTP responses.

### Characteristics
- Full Linux environment in Docker
- Real application deployments
- Real nginx configuration
- Real uWSGI processes
- Real HTTP responses from deployed apps

### Structure
```
tests/d_e2e/
├── docker/
│   ├── Dockerfile.base          # Base image for caching
│   └── Dockerfile               # Test image
├── conftest.py                  # Container fixtures
└── test_simple_apps.py          # Parametrized app tests
```

### Test Applications
E2E tests use sample applications from `apps/test-apps/` and `apps/nix-apps/`:

| App | Type | Status |
|-----|------|--------|
| 000-static | Static HTML | Passing |
| 010-flask-pip-wsgi | Python Flask | Passing |
| 020-nodejs-express | Node.js | Passing |
| 030-golang-gin | Go | Passing |
| 040-sinatra | Ruby | Passing |
| 100-flask-gunicorn-pip | Python + Gunicorn | Passing |
| 110-flask-gunicorn-poetry | Python + Poetry | Skipped |
| 130-golang-minimal | Go minimal | Passing |

**Nix-based Apps** (from `apps/nix-apps/`):

| App | Type | Status |
|-----|------|--------|
| flask-hello | Flask + Nix | Requires Nix |

Each test app includes:
- Application source code
- `Procfile` or `hop3.toml`
- A `[test]` section in `hop3.toml` (or, for Procfile-only apps, a standalone `test.toml`)
- Optional `check.py` validation script

### Current Status
**17 tests collected, 7 passing, 1 skipped**

### Guidelines
- Each test should be independent and idempotent
- Use unique app names (timestamps or UUIDs)
- Clean up deployed apps in teardown
- Test should complete in < 60 seconds per app
- Log container output on failure

---

## hop3-test: Unified Test Runner

In addition to pytest, Hop3 provides `hop3-test` for deployment testing.

### Two Testing Modes

**System Testing** (Testing Hop3):
```bash
hop3-test system --docker          # Deploy and test
hop3-test system --docker --reuse  # Reuse existing
hop3-test system --ssh --host X    # Remote server
```

**App Testing** (Testing Applications):
```bash
hop3-test apps                     # All apps
hop3-test apps 010-flask           # Specific app
```

### Quick Modes
```bash
hop3-test dev      # Fast P0 tests
hop3-test ci       # CI-level tests
hop3-test nightly  # Full test suite
```

See [`cheat-sheet.md`](./cheat-sheet.md) for complete CLI reference.

---

## Running Tests

### Run All Tests
```bash
# All pytest tests (unit + integration)
make test

# Full CI suite (includes system tests)
make test-ci
```

### Run Specific Layers
```bash
# Unit tests only (fast)
uv run pytest packages/hop3-server/tests/a_unit/

# Integration tests only
uv run pytest packages/hop3-server/tests/b_integration/

# System integration tests (requires Docker)
uv run pytest packages/hop3-server/tests/c_system/

# Full E2E tests (requires Docker)
uv run pytest packages/hop3-server/tests/d_e2e/
```

### Run Specific Test Files
```bash
# Single file
uv run pytest tests/a_unit/test_archives.py

# Single test
uv run pytest tests/a_unit/test_archives.py::test_is_safe_filename_accepts_normal_paths

# Tests matching pattern
uv run pytest -k "auth"
```

### Debug Options
```bash
# Verbose output
uv run pytest -v

# Show print statements
uv run pytest -s

# Stop on first failure
uv run pytest -x

# Enter debugger on failure
uv run pytest --pdb
```

---

## Test Coverage

### Current Test Counts

| Layer | Tests | Target |
|-------|-------|--------|
| Unit Tests | 361 | 400+ |
| Integration Tests | 247 | 300+ |
| System Integration | 13 | 30+ |
| Full E2E | 17 | 25+ |
| **Total** | **638** | **755+** |

### Coverage Goals
- **Overall code coverage**: Target > 75%
- **Core modules**: Target > 85%
  - `hop3/orm/` (models)
  - `hop3/commands/` (CLI commands)
  - `hop3/server/` (web server)
  - `hop3/plugins/build/` (builders)

---

## Best Practices

### Test Naming
```python
# Good
def test_deploy_creates_app_directory()
def test_invalid_token_returns_401()
def test_missing_procfile_raises_error()

# Bad
def test_deploy()
def test_auth()
def test_error()
```

### Test Structure (Arrange-Act-Assert)
```python
def test_create_user_with_valid_data():
    # Arrange
    username = "testuser"
    email = "test@example.com"
    password = "secure123"

    # Act
    user = User.create(username, email, password)

    # Assert
    assert user.username == username
    assert user.email == email
    assert user.verify_password(password)
```

### Fixtures Over Setup/Teardown
```python
# Good
@pytest.fixture
def temp_app_dir(tmp_path):
    app_dir = tmp_path / "myapp"
    app_dir.mkdir()
    yield app_dir
    # Cleanup automatic with tmp_path


def test_something(temp_app_dir):
    # Use fixture
    pass


# Avoid
def setup_method():
    self.app_dir = Path("/tmp/myapp")
    self.app_dir.mkdir()


def teardown_method():
    shutil.rmtree(self.app_dir)
```

### Parametrized Tests
```python
@pytest.mark.parametrize(
    "filename,expected",
    [
        ("foo.txt", True),
        ("../etc/passwd", False),
        ("dir/foo.txt", True),
        ("foo/../../etc/passwd", False),
    ],
)
def test_is_safe_filename(filename, expected):
    assert is_safe_filename(filename) == expected
```

---

## Troubleshooting

### System Tests Fail to Start Container
```bash
# Check Docker daemon
docker info

# Check image exists
docker images | grep hop3

# Rebuild image
hop3-test build-test-image --no-cache
```

### E2E Tests Fail
```bash
# View container logs
docker logs hop3-test

# Keep container for debugging
hop3-test system --docker --keep
```

### Tests Pass Locally but Fail in CI
- Check environment variables
- Verify GitHub Actions has enough resources
- Check for timing issues (add appropriate waits)
- Review CI logs for error messages

---

## References

- [pytest Documentation](https://docs.pytest.org/)
- [Litestar Testing](https://litestar.dev/usage/testing.html)
- [Testing Best Practices](https://docs.python-guide.org/writing/tests/)
