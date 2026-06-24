# Hop3 Testing Strategy

> **Updated by ADR 043.** The pytest pyramid is now **three** layers — `a_unit` (fast, no Docker) · `b_integration` (in-process, real in-memory DB, no Docker) · `c_e2e` (Docker/real-deploy, renamed from `d_e2e`). The old `c_system` layer is **dissolved**. A test's layer is decided by whether it needs Docker/root/host-mutation, not by complexity; coverage is measured on `a_unit` + `b_integration` only (e2e runs out-of-process). Markers (`fast`/`integration`/`e2e`/`needs_docker`) are stamped from the directory layer (root `conftest.py`), so `pytest -m fast` / `-m "not needs_docker"` work everywhere.
>
> **Entry points:** `make test-fast` (unit, all packages, < 1 min) · `make test` (check tier: in-process across all 6 packages) · `make test-e2e` (Docker e2e) · `make test-apps` / `test-app APP=…` (deploy real apps via `hop3-test`) · `make test-nightly`.

## Overview

Hop3 uses a comprehensive testing strategy combining two complementary approaches:

1. **pytest-based Test Layers** - Three layers placed by need: unit, integration, and E2E
2. **Application Deployment Testing** - Testing real app deployments via `hop3-test`

This document describes both approaches, their purposes, and how to use them effectively.

## Testing Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Testing Strategy                             │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  pytest Layers              │  Application Testing (hop3-test)      │
│  ─────────────              │  ──────────────────────────────────── │
│                             │                                       │
│  ┌─────────────┐            │  ┌─────────────────────────────────┐  │
│  │   E2E       │ Docker     │  │  hop3-test system               │  │
│  │  (c_e2e/)   │            │  │  - Deploys Hop3 (hop3-deploy)   │  │
│  ├─────────────┤            │  │  - Tests Hop3 + app catalog     │  │
│  │ Integration │            │  │  - Docker or SSH targets        │  │
│  │(b_integr./) │            │  └─────────────────────────────────┘  │
│  ├─────────────┤            │                                       │
│  │   Unit      │ Fast       │  ┌─────────────────────────────────┐  │
│  │  (a_unit/)  │            │  │  hop3-test cloud                │  │
│  └─────────────┘            │  │  - Real cloud servers (Hetzner) │  │
│                             │  │  - Single or multi-distro       │  │
│                             │  │  - Reset / deploy / test phases │  │
│                             │  └─────────────────────────────────┘  │
│                             │                                       │
└─────────────────────────────────────────────────────────────────────┘
```

## Part 1: pytest Test Layers

### The Testing Pyramid

```
           /\
          /  \  E2E Tests (c_e2e/)
         /    \  - Real Docker deployments
        /------\  - No coverage (runs out-of-process)
       /        \
      / Integr.  \ Integration Tests (b_integration/)
     /   Tests    \ - In-process, real in-memory DB
    /--------------\ - Component interactions, no Docker
   /                \
  /   Unit Tests     \ Unit Tests (a_unit/)
 /     (a_unit/)      \ - Fastest, most isolated
/______________________\ - No Docker, counts toward coverage
```

A test's layer is decided by **what it needs** — Docker, root, or host-mutation — not by complexity. Anything that needs a real Docker deploy lives in `c_e2e`; everything that can run in-process (even with a real in-memory database) lives in `a_unit` or `b_integration`. Duplication across layers is allowed.

### Test Layer Characteristics

| Layer | Docker? | Coverage? | Scope | Dependencies | When to Run |
|-------|---------|-----------|-------|--------------|-------------|
| Unit (`a_unit`) | no | yes | Individual functions/classes | None / in-memory SQLite | Every save (`make test-fast`) |
| Integration (`b_integration`) | no | yes | Multiple components, in-process | Real in-memory DB | Before commit (`make test`) |
| E2E (`c_e2e`) | yes | no | Complete workflows, real deploy | Docker + apps | `make test-e2e` + nightly |

### Layer 1: Unit Tests

**Location**: `packages/hop3-server/tests/a_unit/`

**Purpose**: Test individual functions and classes in complete isolation.

**Characteristics**:
- Fast execution (< 1 second total)
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
        "method": "auth register",
        "params": {"username": "test", "password": "secret123"}
    })
    assert response.status_code == 200

    # Login
    response = client.post("/rpc", json={
        "method": "auth login",
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

### Layer 3: E2E Tests

**Location**: `packages/hop3-server/tests/c_e2e/`

> The old `c_system` layer is **dissolved**: its one in-process test moved into `b_integration`, and the rest of its responsibilities were folded into this E2E layer. `c_e2e` is the former `d_e2e`, renamed.

**Purpose**: Test complete workflows in a production-like Docker environment with real deployments.

**Characteristics**:
- Slow execution (real Docker deploys, includes image build)
- Docker containers with the full hop3 stack (server, SSH, HTTP, apps)
- Real deployment workflows (backups, git-push, tarball deploy)
- Does **not** count toward coverage (runs out-of-process)
- `HOP3_UNSAFE=true` configured in the Dockerfile

**Coverage**:
- App deployment via tarball and git hook
- App lifecycle (deploy, list, destroy)
- Python Flask/Django app deployment
- Full deployment lifecycle and HTTP endpoint verification
- Security tests

**Running**:
```bash
# Ensure HOP3_DEV_HOST is not set
unset HOP3_DEV_HOST
pytest packages/hop3-server/tests/c_e2e/ -v
# or, via the make target:
make test-e2e
```

---

## Part 2: Application Deployment Testing (hop3-test)

The `hop3-test` CLI provides a dedicated system for testing application deployments against Hop3. This complements the pytest layers by focusing on real-world deployment scenarios.

### Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                              hop3-test                              │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌───────────────┐    ┌───────────────┐    ┌───────────────┐        │
│  │ Test Catalog  │    │  Test Runner  │    │   Reporters   │        │
│  │ - Scans apps  │    │ - Deploys     │    │ - Console     │        │
│  │ - hop3.toml   │    │ - Validates   │    │ - HTML        │        │
│  │ - Selection   │    │ - Cleanup     │    │ - Recap       │        │
│  └───────┬───────┘    └───────┬───────┘    └───────────────┘        │
│          │                    │                                     │
│          └─────────┬──────────┘                                     │
│                    │                                                │
│  ┌─────────────────┴──────────────────────────────────────────┐     │
│  │                     Deployment Targets                     │     │
│  ├──────────────────────────────┬─────────────────────────────┤     │
│  │ DockerTarget                 │ RemoteTarget                │     │
│  │ - hop3-deploy --docker       │ - SSH to server             │     │
│  │ - Fresh install or --reuse   │ - Existing or fresh Hop3    │     │
│  │ - Local / Docker testing     │ - Remote / production test  │     │
│  └──────────────────────────────┴─────────────────────────────┘     │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### Test Catalog System

The test catalog discovers and manages test applications by scanning for `hop3.toml` files and reading their `[test]` section.

#### Test App Directory Structure

Two conventions coexist:

**Apps with full `hop3.toml`** (all `apps/real-apps-*`, `apps/test-apps-nix/`, `apps/bad/`): test configuration lives in the app's `hop3.toml` under `[test]`. No separate `test.toml` file.

```
apps/real-apps-nix-gen/listmonk/
├── hop3.toml          # [metadata], [build], [[addons]], [test], …
└── (no test.toml)
```

**Apps without `hop3.toml`** (procfile-only test apps, negative-test cases, demos, tutorials): use a standalone `test.toml` file. This covers the historical Procfile-based test harness and a few special shapes the main config doesn't model.

```
apps/test-apps-procfile/010-flask-pip-wsgi/
├── app.py
├── requirements.txt
├── Procfile
└── test.toml          # Procfile-only: no hop3.toml, needs test.toml
```

#### `[test]` Section in hop3.toml (primary shape)

```toml
[metadata]
id = "flask-hello"
description = "Basic Flask application"

[build]
builder = "nix"

[healthcheck]
path = "/"

[test]
priority = "P0"                    # P0 | P1 | P2
tier = "fast"                      # report label only (not a timeout)
targets = ["docker", "remote"]
author = "hop3-team"
covers = ["python", "flask", "pip", "uwsgi"]

[[test.validations]]
path = "/"
status = 200
contains = "Hello"

[[test.validations]]
path = "/api/health"
status = 200
```

Everything else (name, category, services, deployment type) is derived automatically from the surrounding `hop3.toml`. See [config.md](../reference/config.md#test-test-harness-metadata) for the field-by-field reference.

#### Legacy `test.toml` Configuration

For Procfile-only apps, demos, tutorials, and negative-test cases. Same fields, just wrapped in a top-level `[test]` rather than sitting inside `hop3.toml`:

```toml
[test]
name = "010-flask-pip-wsgi"
category = "deployment"
priority = "P0"
tier = "fast"

[test.requirements]
targets = ["docker", "remote"]
services = []

[[validations]]
type = "http"
path = "/"
[validations.expect]
status = 200
```

### Test Modes

The `--mode` profile selects which tests run, filtering by tier and priority (a few profiles instead pin an explicit curated list). The default is `smoke`:

| Mode | Tiers | Priorities | Targets | Use Case |
|------|-------|------------|---------|----------|
| `smoke` | fast | P0 | docker | Smallest sanity check (default) |
| `ci` | fast, medium | P0 | docker | Pre-merge gate |
| `curated` | explicit list | explicit list | docker | Hand-picked diverse slice (< 30 min) |
| `tag-coverage` | fast, medium, slow | P0, P1 | docker | Minimal subset hitting every tag once |
| `combo-coverage` | fast, medium, slow | P0, P1 | docker | Minimal subset hitting every tag combination |
| `nightly` | fast, medium, slow | P0, P1 | docker, remote | Broad nightly run |
| `full` | all | all | docker, remote | Full release validation |

The old names `dev` and `release` remain accepted as aliases for `smoke` and `full`.

```bash
# Smoke mode (default) - fast + P0 deployment apps
hop3-test system --docker

# CI mode - fast + medium, P0
hop3-test system --docker --mode ci

# Full release validation
hop3-test system --docker --mode full
```

### Deployment Targets

#### DockerTarget (`--docker`)

Uses `hop3-deploy --docker` to create a fresh Hop3 installation in a Docker container.

**Use case**: Testing Hop3 itself (installation, deployment pipeline) and the app catalog on a local machine.

```bash
hop3-test system --docker                       # Deploy local code, run defaults
hop3-test system --docker --deploy-from git     # Deploy from a git branch
hop3-test system --docker --clean --with all    # Clean install with all addons
hop3-test system --docker --reuse <app-path>    # Reuse the running container
```

**What happens**:
1. Starts a Docker container (default image `debian:bookworm`)
2. Runs `hop3-deploy --docker --local` to install Hop3
3. Starts services (nginx, PostgreSQL, uWSGI emperor, hop3-server)
4. Runs the selected test apps sequentially
5. Collects diagnostics on failure
6. Cleans up the container (unless `--keep`)

To iterate on a single app against an already-running container, pass `--reuse` together with the app path; this skips redeployment and runs only that app's validations.

```bash
# Deploy the whole catalog on Docker (all addons available)
hop3-test system --docker --clean --with all

# Reuse the container and test one app
hop3-test system --docker --reuse apps/real-apps-native/etherpad
```

#### RemoteTarget (`--ssh`)

Tests against a remote Hop3 server over SSH; the same `--deploy-from` / `--reuse` options apply.

**Use case**: Testing against real servers, staging validation.

```bash
# Deploy to and test a remote server
hop3-test system --ssh --host server.example.com --clean --with all

# Skip deployment and test against the existing server
hop3-test system --ssh --host server.example.com --reuse <app-path>
```

The host can also come from the `HOP3_TEST_HOST` environment variable.

### Test Execution Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Test Execution Flow                          │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  1. Catalog Scan                                                    │
│     ├── Discover hop3.toml [test] + standalone test.toml            │
│     ├── Parse configurations                                        │
│     └── Build test list                                             │
│                                                                     │
│  2. Test Selection                                                  │
│     ├── Apply mode filters (tier, priority)                         │
│     ├── Apply category filters                                      │
│     └── Apply target compatibility                                  │
│                                                                     │
│  3. Target Setup                                                    │
│     ├── Start Docker container (or connect to remote)               │
│     ├── Wait for services ready                                     │
│     └── Verify hop3-server responding                               │
│                                                                     │
│  4. For Each Test:                                                  │
│     ├── Prepare app (copy to temp dir, init git)                    │
│     ├── Deploy (hop3 deploy)                                        │
│     ├── Verify deployment (hop3 app list)                           │
│     ├── Run validations (HTTP checks, custom scripts)               │
│     ├── Collect diagnostics on failure                              │
│     └── Cleanup (hop3 app destroy)                                  │
│                                                                     │
│  5. Reporting                                                       │
│     ├── Print results (PASS/FAIL per test)                          │
│     ├── Summary (total passed/failed, duration)                     │
│     ├── Recap (categories, tiers, technologies)                     │
│     └── Save diagnostic logs                                        │
│                                                                     │
│  6. Cleanup                                                         │
│     └── Stop container (unless --keep)                              │
│                                                                     │
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
- `health_check` - Health verification
- `test` - Test validations
- `cleanup` - Teardown

To replay the saved diagnostic bundle for a failed run, use the run-id printed in the failure headline:

```bash
hop3-test why <run-id>             # Show the failure headline and bundle path
hop3-test why <run-id> --list      # List the sections in the bundle
hop3-test why <run-id> --section proxy   # Replay one section
```

### Test Output

#### Console Output

```
======================================================================
Deploy Hop3 + run tests
======================================================================

Target: docker
Deploy from: local
Clean install: False
Tests to run (8):

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
hop3-test system --docker -q
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
3. **Declare a `[test]` section** in `hop3.toml` (or a standalone `test.toml` for Procfile-only apps): define clear validation criteria
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
# Check tier: unit + integration, all packages, no Docker
make test

# Fast lane: unit only, all packages, no Docker (< 1 min)
make test-fast

# Docker e2e layer (real deploys, backups, git-push)
make test-e2e

# App deployment tests (real apps via hop3-test, Docker)
make test-apps

# Specific pytest layer
pytest packages/hop3-server/tests/a_unit/
pytest packages/hop3-server/tests/b_integration/
pytest packages/hop3-server/tests/c_e2e/

# By marker (stamped from the directory layer by the root conftest.py)
pytest -m fast                 # a_unit + flat unit suites
pytest -m "not needs_docker"   # everything except the Docker e2e layer

# With coverage (in-process layers only; e2e runs out-of-process)
pytest --cov=hop3 --cov-report=html packages/hop3-server/tests/a_unit packages/hop3-server/tests/b_integration

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
```

---

## Part 5: Continuous Integration

### Recommended CI Pipeline

```yaml
# Stage 1: Fast Feedback (every commit)
fast-tests:
  - make lint
  - make test  # Check tier: unit + integration, no Docker

# Stage 2: Docker E2E (every push/PR)
e2e-tests:
  - make test-e2e  # c_e2e layer: real deploys, backups, git-push

# Stage 3: Full App Tests (merge to main)
app-tests:
  - make test-apps  # deploy the app catalog on Docker

# Stage 4: Nightly
nightly:
  - make test-nightly  # full app/demo/tutorial matrix + HTML report
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

### Tests Hang

- Check Docker daemon: `docker ps`
- Use verbose mode: `pytest -v -s` or `hop3-test -v system --docker`
- Check container logs: `docker logs hop3-system-test`
- Check for zombie containers: `docker ps -a | grep hop3`

### Import Errors

```bash
uv sync
```

### Docker Issues

```bash
# Clean up the system-test container
docker rm -f hop3-system-test

# Remove leftover images and start fresh
docker image prune -f
hop3-test system --docker --clean
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
    response = client.post("/rpc", json={"method": "app list"})
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
        json={"method": "user add", "params": {"username": "new-user"}}
    )
    assert response.status_code == 403
```

---

## Part 9: Cloud Testing

For comprehensive E2E testing on real cloud infrastructure, the `hop3-test cloud` command provisions and tests Hop3 on cloud servers. Hetzner Cloud is the default (and currently only) provider; it covers both single-image and multi-distribution runs.

### Commands

```bash
# Single distribution test
hop3-test cloud --image ubuntu-24.04 --apps apps/test-apps-procfile

# Multiple distributions
hop3-test cloud --images ubuntu-24.04,debian-13

# All recommended distros
hop3-test cloud --images all

# List available images
hop3-test cloud --list-images

# Only run tests (skip reset and deploy)
hop3-test cloud --skip-reset --skip-deploy
```

### Supported Distributions

| Image | Description |
|-------|-------------|
| `ubuntu-24.04` | Ubuntu 24.04 LTS (default, well-tested) |
| `debian-13` | Debian 13 (trixie) |
| `debian-12` | Debian 12 (bookworm) |
| `fedora-42` | Fedora 42 |
| `rocky-9` | Rocky Linux 9 (RHEL-compatible) |
| `alma-9` | AlmaLinux 9 (RHEL-compatible) |

### Cloud Test Options

| Option | Description |
|--------|-------------|
| `--provider PROVIDER` | Cloud provider (default: `hetzner`) |
| `--image IMAGE` | Single OS image to test |
| `--images IMAGES` | Comma-separated images, or `all` |
| `--list-images` | List available OS images |
| `--server-id ID` | Use a specific cloud server |
| `--branch BRANCH` | Git branch (default: devel) |
| `--use-local-repo` / `--no-local-repo` | Deploy from local code (default) or from git |
| `--skip-reset` | Skip server reset |
| `--skip-deploy` | Skip Hop3 deployment |
| `--skip-tests` | Skip test execution |
| `--apps DIR` | App directory to test (repeatable) |
| `--with FEATURES` | Comma-separated addons to install (e.g. `--with redis`) |
| `-x`, `--fail-fast` | Stop on first failure |

### Environment Setup

```bash
export HETZNER_API_TOKEN=your_token_here

# Run tests
hop3-test cloud --image ubuntu-24.04
```

### Test Phases

The cloud test orchestrates these phases:

1. **Reset** - Reset server to clean OS state
2. **Deploy** - Install Hop3 from git or local code
3. **Test** - Run configured test suites
4. **Report** - Generate HTML test report

Skip phases with `--skip-reset`, `--skip-deploy`, or `--skip-tests` for debugging.

---

## References

- [Testing Quick Start](testing.md) - Quick reference guide
- [DI Testing Guide](di-testing-guide.md) - Dependency injection testing patterns
- [pytest documentation](https://docs.pytest.org/)
- [Litestar Testing](https://docs.litestar.dev/latest/usage/testing.html) - Litestar test client
- [Dishka documentation](https://dishka.readthedocs.io/)
