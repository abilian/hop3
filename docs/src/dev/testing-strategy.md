# Hop3 Testing Strategy

## Overview

Hop3 uses a comprehensive testing strategy combining two complementary approaches:

1. **pytest-based Test Layers** - Traditional unit, integration, system, and E2E tests
2. **Application Deployment Testing** - Testing real app deployments via `hop3-test`

This document describes both approaches, their purposes, and how to use them effectively.

## Testing Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Testing Strategy                              │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  pytest Layers              │  Application Testing (hop3-test)  │
│  ─────────────              │  ────────────────────────────────────  │
│                             │                                        │
│  ┌─────────────┐            │  ┌─────────────────────────────────┐  │
│  │   E2E       │ Slow       │  │  System Testing                 │  │
│  │  (d_e2e/)   │            │  │  - Uses hop3-deploy             │  │
│  ├─────────────┤            │  │  - Tests Hop3 installation      │  │
│  │   System    │            │  │  - 5-8 known-good apps          │  │
│  │ (c_system/) │            │  └─────────────────────────────────┘  │
│  ├─────────────┤            │                                        │
│  │ Integration │            │  ┌─────────────────────────────────┐  │
│  │(b_integr./) │            │  │  Apps Testing                   │  │
│  ├─────────────┤            │  │  - Uses pre-built image         │  │
│  │   Unit      │ Fast       │  │  - Tests app deployments        │  │
│  │  (a_unit/)  │            │  │  - Multiple test applications   │  │
│  └─────────────┘            │  └─────────────────────────────────┘  │
│                             │                                        │
└─────────────────────────────────────────────────────────────────────┘
```

## Part 1: pytest Test Layers

### The Testing Pyramid

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

### Layer 1: Unit Tests

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

### Layer 2: Integration Tests

**Location**: `packages/hop3-server/tests/b_integration/`

**Purpose**: Test multiple components working together within subsystems.

**Characteristics**:
- Fast execution (~10 seconds)
- Uses real database (in-memory SQLite)
- Uses Litestar TestClient for HTTP
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

### Layer 3: System Tests

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

**Running**:
```bash
# Ensure HOP3_DEV_HOST is not set
unset HOP3_DEV_HOST
pytest packages/hop3-server/tests/c_system/ -v
```

### Layer 4: E2E Tests

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

**Running**:
```bash
pytest packages/hop3-server/tests/d_e2e/ -v
```

---

## Part 2: Application Deployment Testing (hop3-test)

The `hop3-test` CLI provides a dedicated system for testing application deployments against Hop3. This complements the pytest layers by focusing on real-world deployment scenarios.

### Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                       hop3-test                                  │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌───────────────┐    ┌───────────────┐    ┌───────────────┐       │
│  │  Test Catalog │    │  Test Runner  │    │   Reporters   │       │
│  │  - Scans apps │    │  - Deploys    │    │  - Console    │       │
│  │  - test.toml  │    │  - Validates  │    │  - HTML       │       │
│  │  - Selection  │    │  - Cleanup    │    │  - Recap      │       │
│  └───────┬───────┘    └───────┬───────┘    └───────────────┘       │
│          │                    │                                      │
│          └────────────────────┼──────────────────────────────────┐  │
│                               │                                   │  │
│  ┌────────────────────────────┴────────────────────────────────┐ │  │
│  │                    Deployment Targets                        │ │  │
│  ├──────────────────┬──────────────────┬──────────────────────┤ │  │
│  │ DockerDeployTarget│   ReadyTarget    │   RemoteTarget      │ │  │
│  │ - hop3-deploy    │ - Pre-built img  │ - SSH to server     │ │  │
│  │ - Fresh install  │ - Fast startup   │ - Existing Hop3     │ │  │
│  │ - System testing │ - App testing    │ - Production test   │ │  │
│  └──────────────────┴──────────────────┴──────────────────────┘ │  │
│                                                                   │  │
└───────────────────────────────────────────────────────────────────┘  │
```

### Test Catalog System

The test catalog discovers and manages test applications using `test.toml` configuration files.

#### Test App Directory Structure

```
apps/test-apps/
├── 000-static/
│   ├── index.html
│   ├── Procfile
│   └── test.toml          # Test configuration
├── 010-flask-pip-wsgi/
│   ├── app.py
│   ├── requirements.txt
│   ├── Procfile
│   └── test.toml
├── 020-nodejs-express/
│   ├── app.js
│   ├── package.json
│   └── test.toml
└── ...
```

#### test.toml Configuration

```toml
# Test definition for Flask app with pip and uWSGI

[test]
name = "010-flask-pip-wsgi"
category = "deployment"        # deployment, demo, tutorial
tier = "fast"                  # fast, medium, slow, very-slow
priority = "P0"                # P0 (critical), P1 (important), P2 (nice-to-have)
description = "Basic Flask application with pip dependencies and uWSGI"

[test.requirements]
targets = ["docker", "remote"]  # Supported targets
services = []                   # Required services: postgresql, mysql, redis

[test.metadata]
author = "hop3-team"
covers = ["python", "flask", "pip", "uwsgi"]  # Technologies tested

[deployment]
path = "."                     # Path to app within test dir
type = "python"                # App type hint

# Validation rules
[[validations]]
type = "http"
path = "/"
[validations.expect]
status = 200
contains = "Hello"

[[validations]]
type = "http"
path = "/api/health"
[validations.expect]
status = 200
content_type = "application/json"
```

### Test Modes

Test modes define which tests to run based on tier and priority:

| Mode | Tiers | Priorities | Categories | Use Case |
|------|-------|------------|------------|----------|
| `dev` | fast | P0 | deployment | Quick developer verification |
| `ci` | fast, medium | P0 | deployment, demo | CI pipeline |
| `nightly` | fast, medium, slow | P0, P1 | all | Nightly comprehensive |
| `release` | all | all | all | Release validation |

```bash
# Dev mode (default) - ~90 seconds, 5 tests
hop3-test system

# CI mode - ~150 seconds, 8 tests
hop3-test system --mode ci

# Full release validation
hop3-test system --mode release
```

### Deployment Targets

#### DockerDeployTarget (System Testing)

Uses `hop3-deploy --docker` to create a fresh Hop3 installation for each test run.

**Use case**: Testing Hop3 itself (installation, deployment pipeline)

```bash
hop3-test system                    # Default: deploy local code
hop3-test system --deploy-from git  # Deploy from git
hop3-test system --clean            # Clean install
```

**What happens**:
1. Starts Docker container (ubuntu:24.04)
2. Runs `hop3-deploy --docker --local` to install Hop3
3. Starts services (nginx, PostgreSQL, uWSGI emperor, hop3-server)
4. Runs test apps sequentially
5. Collects diagnostics on failure
6. Cleans up container

#### ReadyTarget (App Testing)

Uses a pre-built Docker image (`hop3-ready:latest`) with Hop3 already installed.

**Use case**: Testing applications (fast iteration, skip installation)

```bash
# Build the image first (one-time)
hop3-test build-ready-image

# Run app tests
hop3-test apps                      # All apps
hop3-test apps 010-flask-pip-wsgi   # Specific app
hop3-test apps --category python    # By category
```

**What happens**:
1. Starts container from `hop3-ready:latest`
2. Services already running
3. Runs test apps sequentially
4. Validates HTTP endpoints
5. Cleans up apps between tests

#### RemoteTarget (Remote Server Testing)

Tests against an existing Hop3 server via SSH.

**Use case**: Testing against real servers, staging validation

```bash
hop3-test apps --target remote --host server.example.com
```

### Test Execution Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Test Execution Flow                           │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  1. Catalog Scan                                                     │
│     ├── Discover test.toml files                                    │
│     ├── Parse configurations                                        │
│     └── Build test list                                             │
│                                                                      │
│  2. Test Selection                                                   │
│     ├── Apply mode filters (tier, priority)                         │
│     ├── Apply category filters                                      │
│     └── Apply target compatibility                                  │
│                                                                      │
│  3. Target Setup                                                     │
│     ├── Start Docker container (or connect to remote)               │
│     ├── Wait for services ready                                     │
│     └── Verify hop3-server responding                               │
│                                                                      │
│  4. For Each Test:                                                   │
│     ├── Prepare app (copy to temp dir, init git)                    │
│     ├── Deploy (hop3 app:deploy)                                    │
│     ├── Verify deployment (hop3 apps)                               │
│     ├── Run validations (HTTP checks, custom scripts)               │
│     ├── Collect diagnostics on failure                              │
│     └── Cleanup (hop3 app:destroy)                                  │
│                                                                      │
│  5. Reporting                                                        │
│     ├── Print results (PASS/FAIL per test)                          │
│     ├── Summary (total passed/failed, duration)                     │
│     ├── Recap (categories, tiers, technologies)                     │
│     └── Save diagnostic logs                                        │
│                                                                      │
│  6. Cleanup                                                          │
│     └── Stop container (unless --keep)                              │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### Validation Types

#### HTTP Validation

```toml
[[validations]]
type = "http"
path = "/"
method = "GET"                 # GET, POST, etc.
[validations.expect]
status = 200
contains = "Hello World"       # Body contains string
content_type = "text/html"     # Content-Type header
```

#### Custom Script Validation

Apps can include a `check.py` script for custom validation:

```python
# check.py
import httpx

def check(hostname: str, port: int) -> bool:
    """Custom validation logic."""
    response = httpx.get(
        f"http://{hostname}:{port}/api/health",
        follow_redirects=True
    )
    data = response.json()
    return data.get("status") == "healthy"
```

### Diagnostic Collection

When tests fail, the system collects diagnostic information:

```
test-logs/
└── 20260110_155610/
    └── system-hop3-test-docker/
        ├── diagnostics.json      # Structured diagnostics
        ├── phases.json           # Phase timing
        ├── nginx-error.log       # nginx logs
        ├── nginx-access.log
        ├── uwsgi.log             # uWSGI emperor logs
        ├── hop3-server.log       # Server logs
        └── app-specific/
            └── 010-flask.log     # Per-app logs
```

Diagnostic phases:
- `setup` - Target initialization
- `deploy` - Deployment command
- `service_start` - Service startup
- `health_check` - Health verification
- `validation` - Test validations

### Test Output

#### Console Output

```
======================================================================
SYSTEM TESTING MODE
Testing Hop3 itself with known-good applications
======================================================================

Deploy from: local
Test mode: ci (CI tests (fast+medium + P0 + deployment/demo))
Clean install: False
Tests to run: 8

Deploying Hop3 via hop3-deploy...
[... deployment output ...]

[000-static] Deploying 000-static-1768057582...
✓ HTTP test passed (status: 200)
[PASS] 000-static (7.17s)

[010-flask-pip-wsgi] Deploying 010-flask-pip-wsgi-1768057589...
✓ HTTP test passed (status: 200)
[PASS] 010-flask-pip-wsgi (17.21s)

...

============================================================
All 8 tests passed!
Total time: 148.55s
============================================================

Recap:
  ✓ deployment: 8/8 passed
  Tiers: fast=5, medium=3
  Covers: flask, go, golang, gunicorn, minimal, nginx, nodejs, pip, poetry, ...
  Avg time per test: 18.6s
```

#### Quiet Mode

Use `-q/--quiet` to suppress the recap:

```bash
hop3-test apps -q
```

---

## Part 3: Best Practices

### Writing Tests

1. **Follow the test pyramid**: More unit tests, fewer E2E tests
2. **Test one thing**: Each test should verify one behavior
3. **Use descriptive names**: `test_user_cannot_delete_other_users_apps()`
4. **Arrange-Act-Assert**: Structure tests clearly
5. **Avoid test interdependence**: Tests should be independent and order-agnostic

### Creating Test Apps

1. **Keep apps minimal**: Only include what's needed to test the deployment
2. **Use meaningful names**: `010-flask-pip-wsgi` describes the stack
3. **Include test.toml**: Define clear validation criteria
4. **Set appropriate tier/priority**: fast+P0 for core functionality
5. **Document covers**: List technologies being tested

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

---

## Part 4: Running Tests

### Quick Commands

```bash
# All unit + integration tests
make test

# System tests (Hop3 deployment testing)
make test-system

# App tests
make test-apps

# Specific pytest layer
pytest packages/hop3-server/tests/a_unit/
pytest packages/hop3-server/tests/b_integration/
pytest packages/hop3-server/tests/c_system/
pytest packages/hop3-server/tests/d_e2e/

# With coverage
pytest --cov=hop3 --cov-report=html

# Verbose output
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

# Ensure HOP3_DEV_HOST is not set (for Docker tests)
unset HOP3_DEV_HOST

# Build ready image for app testing
uv run hop3-test build-ready-image
```

---

## Part 5: Continuous Integration

### Recommended CI Pipeline

```yaml
# Stage 1: Fast Feedback (every commit)
fast-tests:
  - make lint
  - make test  # Unit + integration

# Stage 2: System Tests (every push/PR)
system-tests:
  - make test-system  # Dev mode, 5 apps, ~2min

# Stage 3: Full App Tests (merge to main)
app-tests:
  - hop3-test build-ready-image
  - make test-apps  # 66 apps, ~14min

# Stage 4: Nightly
nightly:
  - hop3-test system --mode nightly
```

### Current CI (SourceHut)

- Unit tests
- Integration tests
- Linting and type checking

See: <https://builds.sr.ht/~sfermigier/hop3/>

---

## Part 6: Coverage Targets

| Component | Target | Notes |
|-----------|--------|-------|
| Overall | > 75% | Combined pytest coverage |
| Core modules | > 85% | hop3/core/, hop3/orm/ |
| Commands | > 90% | hop3/commands/ |
| Plugins | > 70% | hop3/plugins/ |

View coverage:
```bash
pytest --cov=hop3 --cov-report=html
open htmlcov/index.html
```

---

## Part 7: Troubleshooting

### "Image hop3-ready:latest not found"

```bash
uv run hop3-test build-ready-image
```

### Tests Hang

- Check Docker daemon: `docker ps`
- Use verbose mode: `pytest -v -s` or `hop3-test apps -v`
- Check container logs: `docker logs hop3-app-test`
- Check for zombie containers: `docker ps -a | grep hop3`

### Import Errors

```bash
uv sync
```

### Docker Issues

```bash
# Clean up containers
docker rm -f hop3-app-test hop3-system-test

# Clean up images
docker rmi hop3-ready:latest

# Rebuild
uv run hop3-test build-ready-image
```

### Authentication Issues

For Docker tests, `HOP3_UNSAFE=true` is set in the container. If tests fail with auth errors:
1. Check the Dockerfile includes `HOP3_UNSAFE=true`
2. Check the container started correctly

---

## Part 8: Security Testing

### HOP3_UNSAFE Mode

For testing in Docker environments, `HOP3_UNSAFE=true` bypasses authentication.

**Warning**: Never use in production. Only for isolated test environments.

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
    token = login_as_user("regular-user")
    response = client.post(
        "/rpc",
        headers={"Authorization": f"Bearer {token}"},
        json={"method": "admin:user:add", "params": {"username": "new-user"}}
    )
    assert response.status_code == 403
```

---

## References

- [Testing Quick Start](testing.md) - Quick reference guide
- [DI Testing Guide](di-testing-guide.md) - Dependency injection testing patterns
- [pytest documentation](https://docs.pytest.org/)
- [Litestar Testing](https://docs.litestar.dev/latest/usage/testing.html) - Litestar test client
- [Dishka documentation](https://dishka.readthedocs.io/)
